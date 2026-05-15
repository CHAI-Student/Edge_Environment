const path = require("path");
const fs = require("fs/promises");
const { v4: uuidv4 } = require("uuid");
const { getClient, publish } = require("./MqttClient");
const config = require("../../config/key");
const { exec } = require("child_process");


const REBOOT_FLAG = path.resolve(__dirname, "../../log/reboot.flag");

let rebooting = false;

async function fileExists(p) {
  try {
    await fs.stat(p);
    return true;
  } catch {
    return false;
  }
}

function makeIFDate() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}${HH}${MM}${SS}`;
}

function runReboot() {
  if (process.platform === "darwin") {
    console.log("[REBOOT] (dev/mac) would reboot now. (skip)");
    return;
  }

  if (process.platform !== "linux") {
    console.warn(`[REBOOT] Unsupported platform: ${process.platform}`);
    return;
  }

  console.log("[REBOOT] rebooting now...");

  exec("sleep 2 && sudo -n systemctl reboot", (err, stdout, stderr) => {
    if (err) {
      console.error("[REBOOT] failed:", err.message);
      return;
    }

    if (stdout) console.log("[REBOOT] stdout:", stdout);
    if (stderr) console.log("[REBOOT] stderr:", stderr);
  });
}

function makeRebootAckPayload({ifSysId, deviceIdx, divisionIdx, resultCd, resultMsg, rebootState}) {
  return {
    HEADER: {
      IF_ID: "IF_01",
      IF_SYSID: ifSysId || uuidv4(),
      IF_HOST: "CRKPNTCHAI",
      IF_DATE: makeIFDate(),
    },
    DATA: {
      device_idx: deviceIdx,
      division_idx: divisionIdx,
      reboot_state: rebootState,
      result_cd: resultCd,
      result_msg: resultMsg,
    },
  };
}

async function publishRebootAck({deviceIdx, divisionIdx, ifSysId, rebootState, resultCd, resultMsg}) {
  const rebootPub = `chai/device/${deviceIdx}/ack/reboot`;

  const payload = makeRebootAckPayload({
    ifSysId,
    deviceIdx,
    divisionIdx,
    rebootState,
    resultCd,
    resultMsg,
  });

  await publish(rebootPub, payload, { qos: 1, retain: false });

  console.log(
    `[REBOOT] ACK published: topic=${rebootPub}, state=${rebootState}, result=${resultCd}`
  );
}

async function publishRebootAckOnce(deviceIdx, divisionIdx) {
  if (!(await fileExists(REBOOT_FLAG))) return;

  let flag = {};

  try {
    const raw = await fs.readFile(REBOOT_FLAG, "utf-8");
    flag = JSON.parse(raw);
  } catch {
    flag = {};
  }

  const ifSysId = flag?.ifSysId || uuidv4();

  try {
    await publishRebootAck({
      deviceIdx,
      divisionIdx,
      ifSysId,
      rebootState: "COMPLETED",
      resultCd: "S",
      resultMsg: "reboot completed",
    });
  } catch (e) {
    console.error("[REBOOT] completed ACK publish failed:", e?.message || e);
  } finally {
    await fs.unlink(REBOOT_FLAG).catch(() => {});
  }
}

async function RebootMqtt() {
  const deviceIdx = config.deviceIdx;
  const divisionIdx = config.divisionIdx;

  if (!deviceIdx || !divisionIdx) {
    console.error("[REBOOT] Missing deviceIdx/divisionIdx in config");
    return;
  }

  const rebootSub = `chai/device/${deviceIdx}/cmd/reboot`;
  const client = getClient();

  client.on("message", async (topic, payload) => {
    if (topic !== rebootSub) return;

    if (rebooting) {
      console.warn("[REBOOT] reboot already in progress. ignore duplicated command.");
      return;
    }

    rebooting = true;

    const text = payload.toString();

    let msg = {};
    try {
      msg = JSON.parse(text);
    } catch {}

    const ifSysId = msg?.HEADER?.IF_SYSID || uuidv4();

    console.log("[MQTT] reboot cmd received. IF_SYSID=", ifSysId);

    try {
      await fs.mkdir(path.dirname(REBOOT_FLAG), { recursive: true });
      await fs.writeFile(
        REBOOT_FLAG,
        JSON.stringify({
          requestedAt: Date.now(),
          ifSysId,
        }),
        "utf-8"
      );

      await publishRebootAck({
        deviceIdx,
        divisionIdx,
        ifSysId,
        rebootState: "ACCEPTED",
        resultCd: "S",
        resultMsg: "reboot accepted",
      });

      console.log("[REBOOT] flag saved. rebooting...");
      runReboot();
    } catch (e) {
      rebooting = false;

      console.error("[REBOOT] reboot handling failed:", e?.message || e);

      await publishRebootAck({
        deviceIdx,
        divisionIdx,
        ifSysId,
        rebootState: "FAILED",
        resultCd: "F",
        resultMsg: e?.message || String(e),
      }).catch(() => {});
    }
  });

  const onReady = async () => {
    console.log("[MQTT] connected (reboot)");

    await publishRebootAckOnce(deviceIdx, divisionIdx);

    console.log("[MQTT] subscribing...", rebootSub);

    client.subscribe(rebootSub, { qos: 1 }, (err, granted) => {
      if (err) {
        console.error("[MQTT] reboot subscribe error:", err.message);
      } else {
        console.log("[MQTT-REBOOT] subscribed:", granted);
      }
    });
  };

  if (client.connected) onReady();
  else client.once("connect", onReady);
}

module.exports = {
  RebootMqtt,
  REBOOT_FLAG,
};

// const path = require("path");
// const fs = require("fs/promises");
// const { v4: uuidv4 } = require("uuid");
// const { getClient, publish } = require("./MqttClient");
// const config = require("../../config/key");
// const { exec } = require("child_process");

// // 실코드/테스트 동일 경로로 고정
// // 운영 중인 상태에 대해서 payment 상태 체크 필요
// const REBOOT_FLAG = path.resolve(__dirname, "../../log/reboot.flag");

// async function fileExists(p) {
//   try { await fs.stat(p); return true; } catch { return false; }
// }

// function runReboot() {
//   // 개발(Mac)에서는 skip
//   if (process.platform === "darwin") {
//     console.log("[REBOOT] (dev/mac) would reboot now. (skip)");
//     return;
//   }

//   // Linux만 허용
//   if (process.platform !== "linux") {
//     console.warn(`[REBOOT] Unsupported platform: ${process.platform}`);
//     return;
//   }

//   console.log("[REBOOT] rebooting now...");

//   // 약간 delay 후 reboot
//   exec("sleep 2 && sudo -n systemctl reboot", (err, stdout, stderr) => {
//     if (err) {
//       console.error("[REBOOT] failed:", err.message);
//       return;
//     }

//     if (stdout) console.log("[REBOOT] stdout:", stdout);
//     if (stderr) console.log("[REBOOT] stderr:", stderr);
//   });
// }

// // 부팅 직후: flag가 있으면 ack 1회 발행하고 flag 삭제
// async function publishRebootAckOnce(client, deviceIdx, divisionIdx) {
//   if (!(await fileExists(REBOOT_FLAG))) return;

//   let flag = {};
//   try {
//     const raw = await fs.readFile(REBOOT_FLAG, "utf-8");
//     flag = JSON.parse(raw);
//   } catch {
//     flag = {};
//   }

//   const ifSysId = flag?.ifSysId || uuidv4();
//   const timestamp = Date.now();

//   const rebootPub = `chai/device/${deviceIdx}/ack/reboot`;

//   const header = {
//     IF_ID: "IF_01",
//     IF_SYSID: ifSysId,
//     IF_HOST: "DEVICE",
//     IF_DATE: timestamp,
//   };

//   const body = {
//     device_idx: deviceIdx,
//     division_idx: divisionIdx,
//     result: "S",
//     message: "reboot completed",
//   };

//   const payload = { HEADER: header, DATA: body };

//   try {
//     await publish(rebootPub, payload, { qos: 1, retain: false });
//     console.log("[REBOOT] reboot ack published:", rebootPub);
//   } catch (e) {
//     console.error("[REBOOT] reboot ack publish failed:", e?.message || e);
//   } finally {
//     // 요구사항: ack publish만 하고 끝내자 → flag는 무조건 제거
//     await fs.unlink(REBOOT_FLAG).catch(() => {});
//   }
// }

// async function RebootMqtt() {
//   const deviceIdx = config.deviceIdx;
//   const divisionIdx = config.divisionIdx;

//   if (!deviceIdx || !divisionIdx) {
//     console.error("[REBOOT] Missing deviceIdx/divisionIdx in config");
//     return;
//   }

//   const rebootSub = `chai/device/${deviceIdx}/cmd/reboot`; // PNT -> Edge
//   const client = getClient();

//   // message 핸들러 (cmd/reboot 수신)
//   client.on("message", async (topic, payload) => {
//     if (topic !== rebootSub) return;

//     const text = payload.toString();
//     let msg = {};
//     try { msg = JSON.parse(text); } catch {}

//     const ifSysId = msg?.HEADER?.IF_SYSID || uuidv4();
//     console.log("[MQTT] reboot cmd received. IF_SYSID=", ifSysId);

//     // reboot 예약 플래그 저장 (부팅 후 ack를 위해)
//     await fs.mkdir(path.dirname(REBOOT_FLAG), { recursive: true });
//     await fs.writeFile(
//       REBOOT_FLAG,
//       JSON.stringify({ requestedAt: Date.now(), ifSysId }),
//       "utf-8"
//     );

//     console.log("[REBOOT] flag saved. rebooting...");
//     runReboot();
//   });

//   const onReady = async () => {
//     console.log("[MQTT] connected (reboot)");

//     // 부팅 직후: flag 있으면 ack 1회 발행 후 삭제
//     await publishRebootAckOnce(client, deviceIdx, divisionIdx);
//     console.log("[REBOOT] publishReboot done");

//     console.log("[MQTT] subscribing...", rebootSub);
//     client.subscribe(rebootSub, { qos: 1 }, (err, granted) => {
//       if (err) console.error("[MQTT] reboot subscribe error:", err.message);
//       else console.log("[MQTT] subscribed:", granted);
//     });
//   };

//   // connect 이벤트 놓침 방지
//   if (client.connected) onReady();
//   else client.once("connect", onReady);
// }

// module.exports = { RebootMqtt, REBOOT_FLAG };