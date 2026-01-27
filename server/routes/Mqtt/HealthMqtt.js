const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const axios = require("axios"); // ✅ API 통신을 위한 라이브러리

async function CardTerminalStatusAPI() {
  let CardTerminalState = '39'
  try {
    console.log(`[CARD-DEVICE] Sending Request to ${config.cardTerminalApi}`);

    // POST 요청 전송
    const response = await axios.get(`${config.cardTerminalApi}/status`, {
      timeout: 30000 // 5초 안에 응답 없으면 에러 처리
    });
    console.log(response.data)

    // API 응답 확인
    const CatResCode = response.data.response_code;
    const CatStatus = response.data.status;
    if (CatResCode == "0" || CatStatus == 'RC_SUCCESS') { // 상태 이상 없음
      CardTerminalState = '39'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "176" || CatStatus == 'RC_TIMEOUT') { // 일정 시간 내 카드 미인식
      CardTerminalState = '32'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "177" || CatStatus == 'RC_CANCEL') { // 단말기에서 토큰 생성 취소
      CardTerminalState = '33'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "178" || CatStatus == 'RC_NOT_CONDITION') { // 단말기에서 토큰 생성 취소
      CardTerminalState = '34'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "179" || CatStatus == 'RC_FORMAT_ERROR') { // 단말기 전문 오류
      CardTerminalState = '35'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "180" || CatStatus == 'RC_CAT_RUNNING') { // 단말기에서 다른 명령어 처리 중
      CardTerminalState = '36'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "181" || CatStatus == 'RC_ERROR_RF') { // RF 카드 인식 오류
      CardTerminalState = '37'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "182" || CatStatus == 'RC_ERROR_VAN') { // 카드 단말기 네트워크 이상
      CardTerminalState = '31'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "192" || CatResCode == "193" || CatStatus == 'RC_ERROR_POS' || CatStatus == 'RC_NETWORK_ERROR') { // 카드 단말기 통신 불량
      CardTerminalState = '30'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "255" || CatStatus == 'RC_ERROR') { // 기타 오류
      CardTerminalState = '38'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } return CardTerminalState
  } catch (error) {
    // 카드 단말기에서 return이 없는 경우 -- timeout
    if (error.code === "ECONNABORTED" || error.code === 'EHOSTUNREACH') {
      CardTerminalState = "30"
      console.log(`[CARD-DEVICE] Card Terminal connect timeout: ${CardTerminalState}`);
    } else if (error.response) {
      CardTerminalState = "30"
      // 서버가 4xx, 5xx 에러를 보낸 경우
      throw new Error(`[CARD-DEVICE] Server Error (${error.response.status}): ${JSON.stringify(error.response.data)}`);
    } else {
      CardTerminalState = "30"
      throw new Error(error.message);
    } return CardTerminalState
  }
}

async function LoadcellStatusAPI() {
  // loadcell status check
  let LoadcellState = '29'
  try {
    console.log(`[IO-BOARD/LOADCELL] Sending Request to ${config.ioboardApi}`);
    const LoadcellRes = await axios.get(`${config.ioboardApi}/loadcell`, { timeout: 5000 });
    console.log(LoadcellRes.data)
    if (LoadcellRes.data.loadcells) {
      console.log('[LOADCELL] Loadcell connect successful')
      LoadcellState = '29'
    } return LoadcellState
  } catch (error) {
    // ioboard timeout
    if (error.code === "ECONNABORTED") {
      LoadcellState = "20"
      console.log(`[LOADCELL] Loadcell connect timeout: ${LoadcellState}`);
    } else if (error.response) {
      // 서버가 4xx, 5xx 에러를 보낸 경우
      LoadcellState = "20"
      throw new Error(`[LOADCELL] Server Error (${error.response.status}): ${JSON.stringify(error.response.data)}`);
    } else {
      LoadcellState = "20"
      throw new Error(error.message);
    } return LoadcellState
  }
}

async function DeadboltStatusAPI() {
  // deadbolt status check
  let DeadboltState = '19'
  try {
    console.log(`[IO-BOARD/DEADBOLT] Sending Request to ${config.ioboardApi}`);
    const DeadboltRes = await axios.get(`${config.ioboardApi}/status`, { timeout: 5000 });
    console.log(DeadboltRes.data)
    if (DeadboltRes.data.door == 'OPENED' && DeadboltRes.data.deadbolt == 'OPENED') {
      DeadboltState = '19'
      console.log(`[DEADBOLT] door is ${DeadboltRes.data.door}, and deadbolt is ${DeadboltRes.data.deadbolt}`)
    } else if (DeadboltRes.data.door == 'CLOSED' && DeadboltRes.data.deadbolt == 'LOCKED') {
      DeadboltState = '19'
      console.log(`[DEADBOLT] door is ${DeadboltRes.data.door}, and deadbolt is ${DeadboltRes.data.deadbolt}`)
    } else if (DeadboltRes.data.door == 'CLOSED' && DeadboltRes.data.deadbolt == 'OPENED') {
      DeadboltState = '10'
      console.log(`[DEADBOLT] door is ${DeadboltRes.data.door}, but deadbolt is ${DeadboltRes.data.deadbolt}`)
    } else if (DeadboltRes.data.door == 'OPENED' && DeadboltRes.data.deadbolt == 'LOCKED') {
      DeadboltState = '10'
      console.log(`[DEADBOLT] door is ${DeadboltRes.data.door}, but deadbolt is ${DeadboltRes.data.deadbolt}`)
    } return DeadboltState
  } catch (error) {
    // deatbolt timeout
    if (error.code === "ECONNABORTED") {
      DeadboltState = "30"
      console.log(`[DEADBOLT] Deadbolt connect timeout: ${DeadboltState}`);
    } else if (error.response) {
      // 서버가 4xx, 5xx 에러를 보낸 경우
      DeadboltState = "30"
      throw new Error(`[CARD-DEVICE] Server Error (${error.response.status}): ${JSON.stringify(error.response.data)}`);
    } else {
      DeadboltState = "30"
      throw new Error(error.message);
    } return DeadboltState
  }
}


async function HealthMqtt() {
  // divisionIdx 기준으로 토픽 네이밍 예시
  const deviceIdx = config.deviceIdx
  const divisionIdx = config.divisionIdx

  // publish
  const healthCheck = `chai/device/${deviceIdx}/health` // healthcare

  const client = getClient(); // 연결 시작
  client.on("connect", () => {
    console.log("[MQTT] connected");
    // const CardTerminalStatus = CardTerminalStatusAPI();
    // const DeadboltStatus = DeadboltStatusAPI();
    // const LoadcellStatus = LoadcellStatusAPI();
    // const LoadcellStatus = "29" // 현재는 값을 못불러오니, 이렇게 지정
    // const CameraStatus = "09" // 현재는 값을 못불러오니, 이렇게 지정
    // const apiCardTerminalStatus = "39" // 현재는 값을 못불러오니, 이렇게 지정
    // const apiDeadboltStatus = "19" // 현재는 값을 못불러오니, 이렇게 지정
    const CameraStatus = "09";
    const DeadboltStatus = '19'
    const LoadcellStatus = '29'

    const publishOnce = async () => {
      // const [CardTerminalStatus, DeadboltStatus, LoadcellStatus] = await Promise.all([
      //   CardTerminalStatusAPI(),
      //   DeadboltStatusAPI(),
      //   LoadcellStatusAPI(),
      // ]);
      const [CardTerminalStatus] = await Promise.all([
        CardTerminalStatusAPI()
      ]);


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
        camera_status: CameraStatus,
        deadbolt_status: DeadboltStatus,
        loadcell_status: LoadcellStatus,
        card_terminal_status: CardTerminalStatus,
        edgepc_status: "49",
      };

      const payload = JSON.stringify({ HEADER: header, DATA: body });
      console.log("Health Check", payload);

      client.publish(healthCheck, payload, { qos: 0, retain: false }, (e) => {
        if (e) console.error("[MQTT] publish error:", e.message);
      });
    };
    publishOnce(); // ✅ 연결 직후 1회
    setInterval(publishOnce, 30000); // ✅ 이후 주기
  });
}

module.exports = { HealthMqtt, CardTerminalStatusAPI, DeadboltStatusAPI, LoadcellStatusAPI };
// module.exports = { HealthMqtt };