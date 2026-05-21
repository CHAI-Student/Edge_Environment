// 파일명: ManualDoor.js
const { v4: uuidv4 } = require("uuid");
const { getClient } = require("./MqttClient");
const config = require("../../config/key");

// 분리한 API 서비스 모듈을 가져옵니다.
const { callApiToControlDeadbolt } = require("./DeadboltApiService");

function formatIfDate(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}`
         + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

// =========================================================
// [메인 로직: MQTT 메시지 처리]
// =========================================================

async function ManualDeadbolt() {
  const deviceIdx = config.deviceIdx;
  const divisionIdx = config.divisionIdx;

  if (!deviceIdx || !divisionIdx) {
    console.error("[DEADBOLT] Missing deviceIdx/divisionIdx in config");
    return;
  }

  const manualDoorSub = `chai/device/${deviceIdx}/cmd/door/manual`;
  const manualDoorPub = `chai/device/${deviceIdx}/ack/door/manual`;

  const client = getClient();

  client.on("connect", () => {
    console.log("[DEADBOLT] MQTT Connected");
    client.subscribe(manualDoorSub, { qos: 1 }, (err, granted) => {
      if (err) console.error("[DEADBOLT] subscribe error:", err.message);
      else console.log("[DEADBOLT] subscribed:", granted);
    });
  });

  client.on("message", async (topic, payloadBuf) => {
    if (topic !== manualDoorSub) return;

    let msg;
    try {
      msg = JSON.parse(payloadBuf.toString());
    } catch (e) {
      console.error("[DEADBOLT] invalid JSON:", payloadBuf.toString());
      return;
    }

    const targetState = msg?.DATA?.door_state; // 'OPEN' or 'CLOSE' // 'UNLOCK' or 'LOCKED'
    const ifSysId = msg?.HEADER?.IF_SYSID || uuidv4();

    console.log(`[DEADBOLT] MQTT CMD Received. ID=${ifSysId}, Target=${targetState}`);

    if (targetState !== "OPEN" && targetState !== "CLOSE") {
      console.error("[DEADBOLT] Invalid deadbolt_state:", targetState);
      return;
    }

    // ---------------------------------------------------------
    // [API 통신 및 결과 처리]
    // ---------------------------------------------------------
    let finalState = "";
    let resultCd = "S"; 
    let resultMsg = "";
    // 다시 검토 필요

    try {
      // 1. 분리된 함수 호출 (API 제어 요청)
      const apiResultState = await callApiToControlDeadbolt(targetState);
      console.log('apiResultState', apiResultState)

      // 2. 결과 검증
      if (apiResultState === "UNLOCK" || apiResultState === "LOCKED") {
        // finalState = apiResultState;
        finalState = apiResultState === "UNLOCK" ? "OPEN" : "CLOSE";
        resultMsg = finalState === "OPEN" ? "Door is opened" : "Door is closed";
      } else {
        throw new Error(`Unexpected API response: ${apiResultState}`);
      }

    } catch (err) {
      console.error("[DOOR] API Control Failed:", err.message);
      resultCd = "F"; 
      resultMsg = "API Error: " + err.message;
      // 실패 시 요청의 반대 상태(또는 기존 상태 유지)로 가정
      finalState = targetState === "UNLOCK" ? "CLOSE" : "OPEN"; 
    }

    // ---------------------------------------------------------
    // [MQTT ACK 전송]
    // ---------------------------------------------------------
    
    const ackPayload = JSON.stringify({
      HEADER: {
        IF_ID: "IF_03",
        IF_SYSID: ifSysId,
        IF_HOST: "CRKPNTCHAI",
        IF_DATE: formatIfDate(),
      },
      DATA: {
        device_idx: deviceIdx,
        division_idx: divisionIdx,
        door_state: finalState,
        result_cd: resultCd,
        result_msg: resultMsg,
      }
    });

    client.publish(manualDoorPub, ackPayload, { qos: 1, retain: false }, (e) => {
      if (e) console.error("[DEADBOLT] Publish Error:", e.message);
      else console.log(`[DEADBOLT] ACK Sent. Result=${resultCd}, State=${finalState}`);
    });
  });

  // 이미 연결되어 있는 경우 구독 처리
  if (client.connected) {
    client.subscribe(manualDoorSub, { qos: 1 });
  }
}

module.exports = { ManualDeadbolt };