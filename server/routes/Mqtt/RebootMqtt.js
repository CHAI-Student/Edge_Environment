const path = require("path");
const fs = require("fs/promises");
const { v4: uuidv4 } = require("uuid");
const { getClient, publish } = require("./MqttClient");
const config = require("../../config/key");
const { exec } = require("child_process");
const { ms } = require("zod/locales");
const ENV_FILE_PATH = path.resolve(__dirname, "../../.env"); // 실제 .env 파일 경로
const { getTrainingStatus, TrainingStore } = require("../RestAPI/TrainingStore");
const { DeviceInfo } = require("../RestAPI/DeviceInfo");
const {notifyAiTrainingStore, fetchCurrentDoorState} = require("./AckCollect")
const {
  DeadboltStatusAPI,
  LoadcellStatusAPI,
  CameraStatusAPI,
} = require("./HealthMqtt");
const jwt = require("jsonwebtoken");
const { is } = require("zod/v4/locales");

const REBOOT_FLAG = path.resolve(__dirname, "../../log/reboot.flag");

let rebooting = false;

async function notifyDeployCompleteForProduct(product) {
  if (!product?.product_idx || !product?.product_eng_name) {
    throw new Error("product_idx or product_eng_name is missing");
  }

  return await notifyAiTrainingStore({
    productIdx: product.product_idx,
    productEngName: product.product_eng_name,
    trainingStatus: "1",
  });
}

// 1. 시스템 서비스 상태 확인 (systemctl)
function checkServiceStatus() {
  return new Promise((resolve) => {
    // OS 쉘에서 systemctl is-active 로 서비스 상태를 확인합니다.
    exec("systemctl is-active edge-environment.service", (err, stdout) => {
      const status = stdout ? stdout.trim() : "unknown";
      if (err || status !== "active") {
        resolve({ ok: false, msg: status || (err && err.message) });
      } else {
        resolve({ ok: true, msg: status });
      }
    });
  });
}

// JWT Access Token 확인
function checkJwtToken() {
  // 실제 환경에서 토큰을 어떻게 받아오는지에 따라 로직을 수정할 수 있습니다.
  // 여기서는 process.env.JWT_TOKEN이 세팅되어 있는지 확인합니다.
  const token = process.env.JWT_TOKEN;
  if (token && typeof token === "string" && token.length > 10) {
    return true;
  }
  return false;
}

// MQTT Connect, Publish, Subscribe 정상 동작 체크
function checkMqttPubSub(client, deviceIdx) {
  return new Promise((resolve) => {
    const testTopic = `chai/device/${deviceIdx}/health/test`;
    const testPayload = "ping_" + Date.now();

    // 임시 메시지 리스너: 내가 보낸 핑(ping)이 잘 돌아오는지 대기
    const testListener = (topic, payload) => {
      if (topic === testTopic && payload.toString() === testPayload) {
        clearTimeout(timeout);
        client.removeListener("message", testListener); // 리스너 해제
        client.unsubscribe(testTopic);                  // 구독 해제
        resolve(true);                                  // 정상 동작 인정
      }
    };

    client.on("message", testListener);

    // 테스트 토픽 구독 후, 동일한 토픽으로 Publish
    client.subscribe(testTopic, { qos: 1 }, (err) => {
      if (err) {
        return resolve(false);
      }
      client.publish(testTopic, testPayload, { qos: 1 });
    });

    // 5초 안에 메시지를 돌려받지 못하면 실패로 간주
    const timeout = setTimeout(() => {
      client.removeListener("message", testListener);
      client.unsubscribe(testTopic);
      resolve(false);
    }, 5000);
  });
}

// 위의 3개 진단을 하나로 묶어 실행하는 종합 함수
async function runStartupDiagnostics(client, deviceIdx) {
  console.log("\n========== [Reboot Diagnostics] ==========");
  console.log("재부팅 완료 감지됨. 시스템 자가 진단을 시작합니다...");

  // 1. 서비스 상태 체크
  const srv = await checkServiceStatus();
  console.log(`[Diagnostic] 1. edge-environment.service : ${srv.ok ? '✅ OK' : '❌ FAIL'} (${srv.msg})`);

  // 2. JWT 토큰 체크
  const jwtOk = checkJwtToken();
  console.log(`[Diagnostic] 2. JWT Access Token : ${jwtOk ? '✅ OK' : '❌ FAIL'}`);

  // 3. MQTT Pub/Sub 체크
  const mqttOk = await checkMqttPubSub(client, deviceIdx);
  console.log(`[Diagnostic] 3. MQTT Pub/Sub Check : ${mqttOk ? '✅ OK' : '❌ FAIL (Timeout/Error)'}`);

  console.log("==========================================\n");
  
  return srv.ok && jwtOk && mqttOk;
}

// ====================================================================
// 💡 .env 파일을 읽어 MODEL_VERSION 값을 영구적으로 변경하는 함수
// ====================================================================
async function updateEnvModelVersion(newVersion) {
  try {
    let envContent = "";
    
    // .env 파일이 존재하는지 확인 후 읽기
    if (await fileExists(ENV_FILE_PATH)) {
      envContent = await fs.readFile(ENV_FILE_PATH, "utf-8");
    }

    // 정규식을 사용해 기존 MODEL_VERSION=... 줄을 찾아서 교체
    const regex = /^MODEL_VERSION=.*$/m;
    if (regex.test(envContent)) {
      envContent = envContent.replace(regex, `MODEL_VERSION=${newVersion}`);
    } else {
      // 기존에 MODEL_VERSION 항목이 없었다면 맨 아랫줄에 추가
      envContent += `\nMODEL_VERSION=${newVersion}\n`;
    }

    // 수정된 내용으로 .env 파일 덮어쓰기
    await fs.writeFile(ENV_FILE_PATH, envContent, "utf-8");
    
    // 현재 실행 중인 프로세스의 메모리 환경변수도 즉시 업데이트
    process.env.MODEL_VERSION = newVersion;
    
    console.log(`[ENV] .env 파일 영구 업데이트 완료: MODEL_VERSION=${newVersion}`);
  } catch (error) {
    console.error(`[ENV] .env 파일 업데이트 중 오류 발생:`, error.message);
    throw error; // 실패 시 상위로 에러를 던져 재부팅을 막습니다.
  }
}

// ====================================================================
// 💡 Docker 이미지를 Pull 받아오는 Helper 함수
// ====================================================================
function pullDockerImage(username, image_name, tag) {
  return new Promise((resolve, reject) => {
    const command = `docker pull ${username}/${image_name}:${tag}`;

    console.log(`[DOCKER] 모델 다운로드 시작: ${command}`);

    // exec를 통해 OS 쉘에 명령어 전달
    exec(command, (err, stdout, stderr) => {
      if (err) {
        console.error(`[DOCKER] 다운로드 실패: ${err.message}`);
        return reject(err);
      }
      
      // 도커 명령어의 진행 과정(경고 등)이 stderr로 출력될 수 있음
      if (stderr && !stderr.includes("Downloaded newer image")) {
        console.warn(`[DOCKER] stderr: ${stderr}`);
      }
      
      console.log(`[DOCKER] 다운로드 완료:\n${stdout}`);
      resolve(true);
    });
  });
}

async function ProductCollectionHealth() {

  const [
    CameraStatus,
    DeadboltHealth,
    LoadcellHealth,
    CurrentDoorState,
  ] = await Promise.all([
    CameraStatusAPI(),
    DeadboltStatusAPI(),
    LoadcellStatusAPI(),
    fetchCurrentDoorState(),
  ]);

  const isHealthOk =
    CameraStatus === "09" &&
    DeadboltHealth === "19" &&
    LoadcellHealth === "29";

  console.log('[ACK-CHECK] isHealthOk: ', isHealthOk)

  return isHealthOk;
}

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

//"수동 : MANUAL
//임베딩 : EMBEDDING"	 조건문 달아야함

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

    if (msg?.DATA?.reboot_mode === "MANUAL"){
      const currentStatus = getTrainingStatus();
      if (currentStatus === "7") {
        console.log(`[RebootMqtt(ModelEmbedding)] 수동(MANUAL) 재부팅 조건 충족 (training_status: 7)`);
        try {
            console.log(`[MQTT] IF_13(장비 정보) 조회를 시작합니다...`);
            
            // DeviceInfo.js 함수 실행 (장비 리스트 반환)
            const deviceList = await DeviceInfo(); 

            // 리스트에 데이터가 있는지 확인 (IF_13 정의서에 의하면 비활성화 시 빈 배열 반환 가능)
            if (deviceList && deviceList.length > 0) {
                const myDeviceInfo = deviceList[0];
                
                const modelVersion = myDeviceInfo.model_version;
                const brunchName = myDeviceInfo.brunch_name;
                
                console.log(`✅ [IF_13 체크 완료] 장비 상세 정보:`);
                console.log(`[RebootMqtt(ModelEmbedding)] 모델 버전 (model_version): ${modelVersion}`);
                console.log(`[RebootMqtt(ModelEmbedding)] 브런치 명 (brunch_name): ${brunchName}`);

                if (String(process.env.MODEL_VERSION) != modelVersion){
                  const healthCare = await ProductCollectionHealth();
                  // [수정] 여기에 결제상태(현재 결제가 진행되고 있는 상황인지)를 확인하는 기능 추가해야 될거 같음
                  console.log(`[RebootMqtt(ModelEmbedding)] 헬스체크 결과: ${healthCare}. 재부팅 절차를 이어서 진행합니다.`);
                  console.log(`[RebootMqtt(ModelEmbedding)] 모델 업데이트 필요. (기존: ${process.env.MODEL_VERSION} -> 신규: ${modelVersion})`);
                  try {
                    // DockerHub로 엣지 내 임베딩
                    await pullDockerImage("CHAI", "crk-model", modelVersion); // [수정] docker pull을 이렇게 해도 되는지 확인
                    console.log(`[RebootMqtt(ModelEmbedding)] 신규 모델(Docker Pull) 임베딩이 성공적으로 완료되었습니다.`);
                    // [수정] pull된 임베딩 된 docker를 engine 파일로 바꾸는 과정
                    // -> 이거는 먼저 pt 파일이 어디에 임베딩 되는지 확인하고
                    // -> 그걸 기반으로 기존에 만들었던 sh 파일로 engine 파일로 바꾸면 될듯
                    
                    // 환경변수인 모델 버전 변겅
                    await updateEnvModelVersion(modelVersion);
                  }
                  catch (updateError) {
                    console.error(`[RebootMqtt(ModelEmbedding)] 도커 이미지 다운로드 실패로 재부팅을 취소합니다.`);
                    await publishRebootAck({
                      deviceIdx, divisionIdx, ifSysId,
                      rebootState: "FAILED", resultCd: "F", resultMsg: "Model Image Pull Failed"
                    });
                    rebooting = false;
                    return;
                  }
                } else{
                  console.warn(`[RebootMqtt(ModelEmbedding)] 재부팅 취소: 기존 모델 버전과 조회된 버전이 동일합니다.`);
                  await publishRebootAck({
                    deviceIdx,
                    divisionIdx,
                    ifSysId,
                    rebootState: "FAILED", // 혹은 요구사항에 맞는 상태값(ex: REJECTED)
                    resultCd: "F",
                    resultMsg: "This Division Model Version is SAME"
                  });
                  rebooting = false; // 진행 상태 초기화
                  return; // 더 이상 아래로 내려가지 않고 중단 (실제 재부팅 X)
                }
            } else {
                console.warn(`⚠️ [IF_13] 장비 정보를 성공적으로 가져왔으나 조회된 데이터가 없습니다. (비활성화 상태 등)`);
                rebooting = false; return; // 데이터가 없을 때 재부팅 멈춤
            }
        } catch (error) {
            console.error(`❌ [IF_13] 장비 정보 조회 중 오류 발생:`, error.message);
            rebooting = false; return; // 에러 시 재부팅 프로세스를 중단
        }
      } else {
        console.warn(`[MQTT] 수동(MANUAL) 재부팅 거부: 현재 학습 상태가 7이 아닙니다. (현재: ${currentStatus})`);
        rebooting = false;
        return; 
      }
    }

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

    const isAfterReboot = await fileExists(REBOOT_FLAG);

    if (isAfterReboot) {
      console.log("[RebootMqtt] 재부팅 플래그 발견. 자가 진단을 시작합니다.");

      const isSystemHealthy = await runStartupDiagnostics(client, deviceIdx);

      if (!isSystemHealthy) {
        console.warn("[RebootMqtt] 재부팅 후 자가 진단 실패. IF07 배포 완료를 전송하지 않습니다.");
        return;
      }

      try {
        const results = await notifyDeployCompleteForAllProducts();

        const hasFail = results.some((item) => {
          const resultCd =
            item.result?.result_cd ||
            item.result?.DATA?.result_cd ||
            item.result?.body?.result_cd;

          return resultCd && resultCd !== "S";
        });

        if (hasFail) {
          console.error("[IF07] 일부 상품 배포 완료 전송 실패");
          return;
        }

        console.log("[IF07 after Reboot] 배포 완료(training_status=1) 전송 성공");

        await publishRebootAckOnce(deviceIdx, divisionIdx);
      } catch (notifyErr) {
        console.error("[IF07] 배포 완료 전송 중 에러:", notifyErr.message);
        return;
      }
    } else {
      console.log("[RebootMqtt] 일반 MQTT 연결. 재부팅 후 처리 없음.");
    }

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