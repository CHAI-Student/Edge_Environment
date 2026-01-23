const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const axios = require("axios"); // ✅ API 통신을 위한 라이브러리

const PAYMENT_API_URL = "http://localhost:8001/status"; 

async function callCardTerminalStatusApi() {
  try {
    console.log(`[API] Sending Card Terminal Request to ${PAYMENT_API_URL}`);

    // POST 요청 전송
    const response = await axios.get(PAYMENT_API_URL, {
      timeout: 5000 // 5초 안에 응답 없으면 에러 처리
    });

    console.log(response.data)

    // API 응답 확인 (서버가 반환한 최종 상태)
    // Python 서버는 { "state": "OPEN" } 형태를 반환함
    const CardTerminalStatus = response.data.response_code;
    if (CardTerminalStatus == "OPEN") { // 카드단말기가 이상이 없으면 OPEN으로 온다는 가정 
      const CardTerminalStatus = '39'
      console.log(`[API] Response Received. Card Tenminal Final State Code: ${CardTerminalStatus}`);
      return CardTerminalStatus
    }
    else{ // 이 부분은 정확히 무슨 문제가 있으면 해당 코드를 보낸다라는 가정문이 추가되어야 할거 같음. 지금은 몰라서 에러 코드값인 41로 하였음
      const CardTerminalStatus = "41"
      console.log(`[API] Response Received. Card Tenminal Final State Code: ${CardTerminalStatus}`);
      return CardTerminalStatus
    }

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

async function callIOStatusApi() {
  try {
    console.log(`[API] Sending IO Board Request to ${IO_BOARD_API_URL}`);

    // POST 요청 전송
    const response = await axios.get(IO_BOARD_API_URL, {
      timeout: 5000 // 5초 안에 응답 없으면 에러 처리
    });

    console.log(response.data)

    // API 응답 확인 (서버가 반환한 최종 상태)
    // Python 서버는 { "state": "OPEN" } 형태를 반환함
    
    if (response.data.door == 'CLOSED' && response.data.deadbolt == 'LOCKED') {
      const DeadboltState = '19';
      // { ..., "loadcells": "HEALTHY" or "UNHEALTHY"}
      // camera: { "status": "ok" or "error", "device_count": <connected device count>}
      console.log(`[API] Response Received. Deadbolt Final State Code: ${DeadboltState}`);
      return DeadboltState;
    }
    else{
      const DeadboltState = '20'; // 이 부분은 정확히 무슨 문제가 있으면 해당 코드를 보낸다라는 가정문이 추가되어야 할거 같음. 지금은 몰라서 에러 코드값인 20으로 하였음
      console.log(`[API] Response Received. Deadbolt Final State Code: ${DeadboltState}`);
      return DeadboltState;
    }

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

  const apiCardTerminalStatus = await callCardTerminalStatusApi();
  const apiDeadboltStatus = await callIOStatusApi();
  //나중에 await 처리 하기

  const apiLoadcellStatus = "29" // 현재는 값을 못불러오니, 이렇게 지정
  const apiCameraStatus = "09" // 현재는 값을 못불러오니, 이렇게 지정

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

      // IO 보드 상태값도 보내줘야할지 판단 필요
      const IOBoardStatus = (apiDeadboltStatus == "19" && apiLoadcellStatus == "29") ? "49" : "41";

      const body = {
        device_idx: deviceIdx,
        division_idx: divisionIdx,
        camera_status: apiCameraStatus,
        deadbolt_status: apiDeadboltStatus,
        loadcell_status: apiLoadcellStatus,
        CardTerminalStatus: apiCardTerminalStatus,
        ioboard_status: IOBoardStatus,
        edgepc_status: '49'
      };

      const payload = JSON.stringify({ HEADER: header, DATA: body });
      console.log('Health Check', payload)

      client.publish(healthCheck, payload, { qos: 0, retain: false }, (e) => {
        if (e) console.error("[MQTT] publish error:", e.message);
      });
    }, 60000);
  });
}

module.exports = { HealthMqtt, callCardTerminalStatusApi, callIOStatusApi };