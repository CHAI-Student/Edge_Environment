const { v4: uuidv4 } = require("uuid");
const { getClient } = require("./MqttClient");
const config = require("../../config/key");
const axios = require("axios"); // ✅ API 통신을 위한 라이브러리

// =========================================================
// [API 설정] 도어 컨트롤러(서버)의 주소를 입력하세요.
// =========================================================
// 예: Python FastAPI 서버가 192.168.0.10:8000 에서 실행 중일 경우
const DOOR_API_URL = "http://localhost:8000/deadbolt"; 

// =========================================================
// [API 제어 함수]
// =========================================================

/**
 * API 서버에 도어 제어 요청을 보냅니다.
 * Python 서버의 스펙: POST /deadbolt, Body: { "state": "OPEN" | "CLOSE" }
 */
async function callApiToControlDoor(targetState) {
  try {
    console.log(`[API] Sending Request to ${DOOR_API_URL} (state: ${targetState})...`);

    // POST 요청 전송
    const response = await axios.post(DOOR_API_URL, {
      state: targetState // Python Pydantic 모델에 맞춤
    }, {
      timeout: 5000 // 5초 안에 응답 없으면 에러 처리
    });

    // API 응답 확인 (서버가 반환한 최종 상태)
    // Python 서버는 { "state": "OPEN" } 형태를 반환함
    const finalState = response.data.state;
    console.log(`[API] Response Received. Final State: ${finalState}`);
    
    return finalState;

  } catch (error) {
    // 에러 발생 시 상세 내용 출력
    if (error.response) {
      // 서버가 4xx, 5xx 에러를 보낸 경우
      throw new Error(`Server Error (${error.response.status}): ${JSON.stringify(error.response.data)}`);
    } else if (error.request) {
      // 요청은 보냈으나 응답이 없는 경우 (네트워크 문제)
      throw new Error("No response from server (Network Error)");
    } else {
      throw new Error(error.message);
    }
  }
}

// =========================================================
// [메인 로직: MQTT 메시지 처리]
// =========================================================

async function ManualDoor() {
  const deviceIdx = config.deviceIdx;
  const divisionIdx = config.divisionIdx;

  if (!deviceIdx || !divisionIdx) {
    console.error("[DOOR] Missing deviceIdx/divisionIdx in config");
    return;
  }

  const manualDoorSub = `chai/device/${deviceIdx}/cmd/door/manual`;
  const manualDoorPub = `chai/device/${deviceIdx}/ack/door/manual`;

  const client = getClient();

  client.on("connect", () => {
    console.log("[DOOR] MQTT Connected");
    client.subscribe(manualDoorSub, { qos: 1 }, (err, granted) => {
      if (err) console.error("[DOOR] subscribe error:", err.message);
      else console.log("[DOOR] subscribed:", granted);
    });
  });

  client.on("message", async (topic, payloadBuf) => {
    if (topic !== manualDoorSub) return;

    let msg;
    try {
      msg = JSON.parse(payloadBuf.toString());
    } catch (e) {
      console.error("[DOOR] invalid JSON:", payloadBuf.toString());
      return;
    }

    const targetState = msg?.DATA?.door_state; // 'OPEN' or 'CLOSE'
    const ifSysId = msg?.HEADER?.IF_SYSID || uuidv4();

    console.log(`[DOOR] MQTT CMD Received. ID=${ifSysId}, Target=${targetState}`);

    if (targetState !== "OPEN" && targetState !== "CLOSE") {
      console.error("[DOOR] Invalid door_state:", targetState);
      return;
    }

    // ---------------------------------------------------------
    // [API 통신 및 결과 처리]
    // ---------------------------------------------------------
    let finalState = "UNKNOWN";
    let resultCd = "S"; 
    let resultMsg = "";

    try {
      // 1. API 호출 (제어 및 상태 확인을 한 번에 수행)
      // Python 서버 로직상 제어 후 결과 상태를 반환하므로, 별도의 get_status가 필요 없음
      const apiResultState = await callApiToControlDoor(targetState);

      // 2. 결과 검증
      if (apiResultState === "OPEN" || apiResultState === "CLOSE") {
        finalState = apiResultState;
        resultMsg = finalState === "OPEN" ? "Door is opened" : "Door is closed";
      } else {
        throw new Error(`Unexpected API response: ${apiResultState}`);
      }

    } catch (err) {
      console.error("[DOOR] API Control Failed:", err.message);
      resultCd = "F"; 
      resultMsg = "API Error: " + err.message;
      // 실패 시 요청의 반대 상태(또는 알 수 없음)로 가정
      finalState = targetState === "OPEN" ? "CLOSE" : "OPEN"; 
    }

    // ---------------------------------------------------------
    // [MQTT ACK 전송]
    // ---------------------------------------------------------
    const timestamp = Date.now();
    const ackPayload = JSON.stringify({
      HEADER: {
        IF_ID: "IF_03",
        IF_SYSID: ifSysId,
        IF_HOST: "CHAI",
        IF_DATE: timestamp,
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
      if (e) console.error("[DOOR] Publish Error:", e.message);
      else console.log(`[DOOR] ACK Sent. Result=${resultCd}, State=${finalState}`);
    });
  });

  if (client.connected) {
    client.subscribe(manualDoorSub, { qos: 1 });
  }
}

module.exports = { ManualDoor };