/* eslint-disable no-console */
const path = require("path");
const fs = require("fs/promises");
const { spawn } = require("child_process");
const mqtt = require("mqtt");
const config = require('../config/key')

// 프로젝트에 맞게 조정
const SERVER_ENTRY = path.resolve(__dirname, "../index.js");

// RebootMqtt에서 쓰는 reboot.flag 경로와 반드시 동일해야 함
const REBOOT_FLAG = path.resolve(__dirname, "../log/reboot.flag");

// 환경변수(또는 config/key가 읽는 값)에서 가져오기
const MQTT_URL = config.mqttURL;   // 예: mqtt://chaidev.atcrk.co.kr:1883
const MQTT_USER = config.mqttID;   // 예: pnt
const MQTT_PASS = config.mqttPW;   // 예: chai
const DEVICE_IDX = config.deviceIdx; // 예: DE17560868094789999
const DIVISION_IDX = config.divisionIdx; // 예: DI17647205538493077

if (!MQTT_URL || !MQTT_USER || !MQTT_PASS || !DEVICE_IDX || !DIVISION_IDX) {
  console.error("Missing env. Required: MQTT_URL, MQTT_USER, MQTT_PASS, DEVICE_IDX, DIVISION_IDX");
  process.exit(1);
}

const CMD_TOPIC = `chai/device/${DEVICE_IDX}/cmd/reboot`;
const ACK_TOPIC = `chai/device/${DEVICE_IDX}/ack/reboot`;

function startServer() {
  console.log("[TEST] starting server:", SERVER_ENTRY);
  const p = spawn(process.execPath, [SERVER_ENTRY], {
    env: {
      ...process.env,
      NODE_ENV: "development",
      PORT: "8000",            // 테스트 전용 포트 (원하는 값)
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  p.stdout.on("data", (d) => process.stdout.write(`[srv] ${d}`));
  p.stderr.on("data", (d) => process.stderr.write(`[srv-err] ${d}`));

  return p;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function fileExists(p) {
  try { await fs.stat(p); return true; } catch { return false; }
}

// function startServer() {
//   console.log("[TEST] starting server:", SERVER_ENTRY);
//   const p = spawn(process.execPath, [SERVER_ENTRY], {
//     env: { ...process.env, NODE_ENV: "development" },
//     stdio: ["ignore", "pipe", "pipe"],
//   });

//   p.stdout.on("data", (d) => process.stdout.write(`[srv] ${d}`));
//   p.stderr.on("data", (d) => process.stderr.write(`[srv-err] ${d}`));

//   return p;
// }

async function stopServer(proc) {
  if (!proc) return;
  console.log("[TEST] stopping server...");
  proc.kill("SIGINT");
  await sleep(700);
  if (!proc.killed) {
    proc.kill("SIGKILL");
  }
}

function connectMqtt() {
  const client = mqtt.connect(MQTT_URL, {
    username: MQTT_USER,
    password: MQTT_PASS,
    clientId: `test-${DEVICE_IDX}-${Date.now().toString(16)}`,
    clean: true,
    keepalive: 30,
    reconnectPeriod: 0,
  });

  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("MQTT connect timeout")), 8000);
    client.once("connect", () => {
      clearTimeout(t);
      resolve(client);
    });
    client.once("error", (e) => {
      clearTimeout(t);
      reject(e);
    });
  });
}

async function publishRebootCmd(mqttClient) {
  const payload = JSON.stringify({
    HEADER: {
      IF_ID: "IF_01",
      IF_SYSID: `test-${Date.now()}`,
      IF_HOST: "TEST",
      IF_DATE: new Date().toISOString(),
    },
    DATA: { division_idx: DIVISION_IDX, device_idx: DEVICE_IDX },
  });

  await new Promise((resolve, reject) => {
    mqttClient.publish(CMD_TOPIC, payload, { qos: 1, retain: false }, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });

  console.log("[TEST] published cmd:", CMD_TOPIC);
}

async function waitForAck(mqttClient, timeoutMs = 10000) {
  console.log("[TEST] waiting ack:", ACK_TOPIC);

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("ACK timeout")), timeoutMs);

    mqttClient.subscribe(ACK_TOPIC, { qos: 1 }, (err) => {
      if (err) {
        clearTimeout(timer);
        return reject(err);
      }
    });

    mqttClient.on("message", (topic, payload) => {
      if (topic !== ACK_TOPIC) return;
      clearTimeout(timer);
      console.log("[TEST] ✅ ack received:", payload.toString());
      resolve();
    });
  });
}

(async () => {
  // 0) 이전 flag가 있으면 지움
  if (await fileExists(REBOOT_FLAG)) {
    console.log("[TEST] removing old reboot flag");
    await fs.unlink(REBOOT_FLAG);
  }

  // 1) 서버 시작
  let server = startServer();
  await sleep(2500); // 서버 부팅 대기

  // 2) MQTT 연결
  const mqttClient = await connectMqtt();
  mqttClient.on("error", (e) => console.error("[TEST] mqtt error:", e.message));

  // 3) reboot cmd publish
  await publishRebootCmd(mqttClient);

  // 4) flag 생성 확인
  for (let i = 0; i < 20; i++) {
    if (await fileExists(REBOOT_FLAG)) break;
    await sleep(200);
  }
  if (!(await fileExists(REBOOT_FLAG))) {
    throw new Error("reboot.flag not created (cmd not handled)");
  }
  console.log("[TEST] reboot.flag created");

  // 5) “재부팅” 대신 서버 재시작
  await stopServer(server);
  await sleep(800);
  server = startServer();
  await sleep(2500);

  await sleep(1000);
  if (await fileExists(REBOOT_FLAG)) {
    throw new Error("reboot.flag still exists (ack flow not completed)");
  }
  console.log("[TEST] reboot flow PASS (flag cleared)");

  // cleanup
  mqttClient.end(true);
  await stopServer(server);

  console.log("\n[TEST] E2E reboot flow PASS");
  process.exit(0);
})().catch((e) => {
  console.error("[TEST] failed:", e);
  process.exit(1);
});
