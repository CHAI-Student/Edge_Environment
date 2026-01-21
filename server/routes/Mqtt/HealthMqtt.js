const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const axios = require("axios"); // ✅ API 통신을 위한 라이브러리

const PAYMENT_API_URL = "http://localhost:8001/status"; 

async function callApiToControlDoor() {
  try {
    console.log(`[API] Sending Request to ${PAYMENT_API_URL}`);

    // POST 요청 전송
    const response = await axios.get(PAYMENT_API_URL, {
      timeout: 5000 // 5초 안에 응답 없으면 에러 처리
    });

    console.log(response.data)

    // API 응답 확인 (서버가 반환한 최종 상태)
    // Python 서버는 { "state": "OPEN" } 형태를 반환함
    const finalState = response.data.response_code;
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

const IO_BOARD_API_URL = "http://localhost:8000/status"; 

async function callApiToControlIO() {
  try {
    console.log(`[API] Sending Request to ${IO_BOARD_API_URL}`);

    // POST 요청 전송
    const response = await axios.get(IO_BOARD_API_URL, {
      timeout: 5000 // 5초 안에 응답 없으면 에러 처리
    });

    console.log(response.data)

    // API 응답 확인 (서버가 반환한 최종 상태)
    // Python 서버는 { "state": "OPEN" } 형태를 반환함
    
    if (response.data.door == 'CLOSED' && response.data.deadbolt == 'LOCKED') {
      const DeadboltState = '0';
      // { ..., "loadcells": "HEALTHY" or "UNHEALTHY"}
      // camera: { "status": "ok" or "error", "device_count": <connected device count>}
      console.log(`[API] Response Received. Final State: ${DeadboltState}`);
      return DeadboltState;
    }
    
    return DeadboltState;

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

async function HealthMqtt() {
  // divisionIdx 기준으로 토픽 네이밍 예시
  const deviceIdx = config.deviceIdx
  const divisionIdx = config.divisionIdx

  const apiResultState = await callApiToControlDoor();
  //나중에 await 처리 하기

  // publish
  const healthCheck = `chai/device/${deviceIdx}/health` // healthcare

  const client = getClient(); // 연결 시작
  client.on("connect", () => {
    console.log("[MQTT] connected");
    
    // health publish interval (connect 이후 시작)
    setInterval(() => {
      const timestamp = Date.now();

      const header = {
        IF_ID: "IF_02",
        IF_SYSID: uuidv4(),
        IF_HOST: "MQTTX",
        IF_DATE: timestamp,
      };

      const body = {
        device_idx: deviceIdx,
        division_idx: divisionIdx,
        camera_status: "09",
        deadbolt_status: "19",
        loadcell_status: "29",
        card_terminal_status: "39",
        edgepc_status: "49"
      };

      const payload = JSON.stringify({ HEADER: header, DATA: body });
      console.log('Health Check', payload)

      client.publish(healthCheck, payload, { qos: 0, retain: false }, (e) => {
        if (e) console.error("[MQTT] publish error:", e.message);
      });
    }, 60000);
  });
}

module.exports = { HealthMqtt };
