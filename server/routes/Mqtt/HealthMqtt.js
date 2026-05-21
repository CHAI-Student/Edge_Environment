const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const axios = require("axios"); // ✅ API 통신을 위한 라이브러리
const { devAutoLogin } = require("../../routes/auth");
async function CardTerminalStatusAPI() {
  let CardTerminalState = '39'
  try {
    console.log(`[CARD-DEVICE] Sending Request to ${config.cardTerminalApi}`);

    // POST 요청 전송
    const response = await axios.get(`${config.cardTerminalApi}/status`, {
      timeout: 30000 // 5초 안에 응답 없으면 에러 처리

    });
    // console.log(response.data)

    // API 응답 확인
    const CatResCode = response.data.response_code;
    const CatStatus = response.data.message;
    if (CatResCode == "0") { // 상태 이상 없음
      CardTerminalState = '39'
      // console.log(`[CARD-DEVICE]: ${CatResCode} / ${CatStatus}`);
    } else if (CatResCode == "176") { // 일정 시간 내 카드 미인식
      CardTerminalState = '32'
      // console.log(`[CARD-DEVICE]: ${CatResCode} / ${CatStatus}`);
    } else if (CatResCode == "177" || CatStatus == 'CANCEL') { // 단말기에서 토큰 생성 취소
      CardTerminalState = '33'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "178" || CatStatus == 'NOT_CONDITION') { // 단말기에서 토큰 생성 취소
      CardTerminalState = '34'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "179" || CatStatus == 'FORMAT_ERROR') { // 단말기 전문 오류
      CardTerminalState = '35'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "180" || CatStatus == 'CAT_RUNNING') { // 단말기에서 다른 명령어 처리 중
      CardTerminalState = '36'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "181" || CatStatus == 'ERROR_RF') { // RF 카드 인식 오류
      CardTerminalState = '37'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "182" || CatStatus == 'ERROR_VAN') { // 카드 단말기 네트워크 이상
      CardTerminalState = '31'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "192" || CatResCode == "193" || CatStatus == 'ERROR_POS' || CatStatus == 'NETWORK_ERROR') { // 카드 단말기 통신 불량
      CardTerminalState = '30'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "255" || CatStatus == 'ERROR') { // 기타 오류
      CardTerminalState = '38'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } return CardTerminalState
  } catch (error) {
    // 카드 단말기에서 return이 없는 경우 -- timeout
    if (error.code === "ECONNREFUSED" || error.code === 'EHOSTUNREACH') {
      CardTerminalState = "30"
      // console.log(`[CARD-DEVICE] Card Terminal connect timeout: ${CardTerminalState}`);
    } else if (error.response) {
      CardTerminalState = "30"
      // 서버가 4xx, 5xx 에러를 보낸 경우
      // throw new Error(`[CARD-DEVICE] Server Error (${error.response.status}): ${JSON.stringify(error.response.data)}`);
    } else {
      CardTerminalState = "30"
      // throw new Error(error.message);
    } return CardTerminalState
  }
}

let IOBoardRes = null; // 전역 변수로 선언하여 LoadcellStatusAPI에서 사용

async function DeadboltStatusAPI() {
  // deadbolt status check
  let DeadboltState = '19'
  try {
    console.log(`[IO-BOARD/DEADBOLT] Sending Request to ${config.ioboardApi}`);
    IOBoardRes = await axios.get(`${config.ioboardApi}/health`, { timeout: 5000 });
    // console.log(IOBoardRes.data)
    if (IOBoardRes.data.deadbolt == 'HEALTHY') {
      DeadboltState = '19'
      // console.log(`[DEADBOLT] deadbolt is ${IOBoardRes.data.deadbolt}`)
    } else if (IOBoardRes.data.deadbolt != 'HEALTHY') {
      DeadboltState = '10'
      // console.log(`[DEADBOLT] deadbolt is ${IOBoardRes.data.deadbolt}`)
    }
    return DeadboltState
  } catch (error) {
    // deadbolt timeout
    if (error.code === "ECONNREFUSED") {
      DeadboltState = "10"
      // console.log(`[DEADBOLT] Deadbolt connect timeout: ${DeadboltState}`);
    } else if (error.response) {
      // 서버가 4xx, 5xx 에러를 보낸 경우
      DeadboltState = "10"
      // console.error(`[DEADBOLT] Server Error (${error.response.status})`);
    } else {
      DeadboltState = "10"
      // console.error(`[DEADBOLT] Error: ${error.message}`);
    }
    return DeadboltState
  }
}

async function LoadcellStatusAPI() {
  // loadcell status check
  let LoadcellState = '29'
  try {
    // IOBoardRes는 DeadboltStatusAPI()에서 이미 호출되었으므로 사용
    if (!IOBoardRes || !IOBoardRes.data) {
      // console.log('[LOADCELL] IOBoardRes is not available');
      LoadcellState = '20'
      return LoadcellState;
    }
    console.log(`[IO-BOARD/LOADCELL] Checking IOBoard response`);
    // console.log(IOBoardRes.data)
    if (IOBoardRes.data.loadcells == 'HEALTHY') {
      // console.log('[LOADCELL] Loadcell connect successful')
      LoadcellState = '29'
    } else {
      LoadcellState = '20'
    }
    return LoadcellState
  } catch (error) {
    // loadcell error
    if (error.code === "ECONNREFUSED") {
      LoadcellState = "20"
      // console.log(`[LOADCELL] Loadcell connect timeout: ${LoadcellState}`);
    } else if (error.response) {
      // 서버가 4xx, 5xx 에러를 보낸 경우
      LoadcellState = "20"
      // console.error(`[LOADCELL] Server Error (${error.response.status})`);
    } else {
      LoadcellState = "20"
      // console.error(`[LOADCELL] Error: ${error.message}`);
    }
    return LoadcellState
  }
}

async function CameraStatusAPI() {
  //camera status check
  let CameraState = ''
  try {
    console.log(`[CAMERA] Sending Request to ${config.cameraApi}`);
    const CameraRes = await axios.get(`${config.cameraApi}/health`, { timeout: 5000 });
    console.log(CameraRes.data)
    if (CameraRes.data.status == 'HEALTHY') {
      CameraState = '09'
      // console.log('[CAMERA] camera connect success')
    } else {
      CameraState = '00'
      // console.log('[CAMERA] camera unconnected: ', CameraRes.data)
    }
    return CameraState
  } catch (error) {
    // camera timeout
    if (error.code === "ECONNREFUSED") {
      CameraState = "00"
      // console.log(`[CAMERA] Camera connect timeout: ${CameraState}`);
    } else if (error.response) {
      // 서버가 4xx, 5xx 에러를 보낸 경우
      CameraState = "00"
      // console.error(`[CAMERA] Server Error (${error.response.status})`);
    } else {
      CameraState = "00"
      // console.error(`[CAMERA] Error: ${error.message}`);
    }
    return CameraState
  }
}

async function EdgePCStatusAPI(DeadboltState, LoadcellState) {
  //edgepc status check
  let edgeStatus = '49';
  let network = false;
  let ModelRes = null;

  try {
    // console.log(`[NETWORK] Network status`);

    // 2. 모델 서버 상태 확인
    console.log(`[MODEL-EDGEPC] Sending Request to ${config.modelApi}`);
    ModelRes = await axios.get(`${config.modelApi}/api/health`, { timeout: 5000 });
    console.log('[MODEL] ModelRes:', ModelRes.data);

    // 3. 상태 판단
    if (LoadcellState == '29' && DeadboltState == '19' && network && ModelRes.data.status == 'ok') {
      // console.log('[EDGEPC] All systems healthy')
      edgeStatus = '49'
    } else if (LoadcellState != '29' && DeadboltState != '19') {
      edgeStatus = '41'
      // console.log('[EDGEPC] IO Board unconnected')
    } 
    // else if (ModelRes.data.model == 'UNHEALTHY') {
    //   edgeStatus = '42'
    //   // console.log('[EDGEPC] Model server unconnected')
    // }
    return edgeStatus

  } catch (error) {
    // 예외 처리
    if (error.code === "ECONNREFUSED") {
      edgeStatus = "43"
      // console.log(`[EDGEPC] Connect ECONNREFUSED: ${edgeStatus}`);
    } else if (error.response) {
      // 서버가 4xx, 5xx 에러를 보낸 경우
      edgeStatus = "42"
      // console.error(`[EDGEPC] Server Error (${error.response.status})`);
    } else {
      edgeStatus = "42"
      // console.error(`[EDGEPC] Error: ${error.message}`);
    }
    return edgeStatus
  }
}


async function HealthMqtt() {
  // divisionIdx 기준으로 토픽 네이밍 예시
  const deviceIdx = config.deviceIdx
  const divisionIdx = config.divisionIdx

  // publish
  const healthCheck = `chai/device/${deviceIdx}/health` // healthcare

  // ai server health-check
  console.log(`[AI SERVER-EDGEPC] Sending Request to ${config.aiServerApi}`);
  const AIServerCheck = await axios.get(`${config.aiServerApi}/health`, { timeout: 5000 });
  console.log('[AI SERVER] AIServerCheck:', AIServerCheck.data);


  const client = getClient(); // 연결 시작
  client.on("connect", () => {
    console.log("[MQTT] connected");
    // const CameraStatus = "09";
    // const DeadboltStatus = '19'
    // const LoadcellStatus = '29'
    // const CardTerminalStatus = '39'

    const publishOnce = async () => {
      // const CardTerminalStatus = await CardTerminalStatusAPI();
      const CardTerminalStatus = '39'
      const DeadboltStatus = await DeadboltStatusAPI();
      const LoadcellStatus = await LoadcellStatusAPI();
      const CameraStatus = await CameraStatusAPI();
      const EdgePCStatus = await EdgePCStatusAPI(DeadboltStatus, LoadcellStatus);
      // const [CardTerminalStatus, DeadboltStatus, LoadcellStatus,] = await Promise.all([
      //   CardTerminalStatusAPI(),
      //   DeadboltStatusAPI(),
      //   LoadcellStatusAPI(),
      // ]);

      const timestamp = Date.now();
      const header = {
        IF_ID: "IF_02",
        IF_SYSID: uuidv4(),
        IF_HOST: "CRKPNTCHAI",
        IF_DATE: timestamp,
      };

      const body = {
        device_idx: deviceIdx,
        division_idx: divisionIdx,
        camera_status: CameraStatus,
        deadbolt_status: DeadboltStatus,
        loadcell_status: LoadcellStatus,
        card_terminal_status: CardTerminalStatus,
        edgepc_status: EdgePCStatus,
      };

      const payload = JSON.stringify({ HEADER: header, DATA: body });
      console.log("Health Check", payload);

      client.publish(healthCheck, payload, { qos: 1, retain: false }, (e) => {
        if (e) console.error("[MQTT] publish error:", e.message);
      });
    };
    // publishOnce(); // ✅ 연결 직후 1회
    setInterval(publishOnce, 30000); // ✅ 이후 주기
    // setInterval(publishOnce, 180000); // ✅ 
  });
}

module.exports = { HealthMqtt, CardTerminalStatusAPI, DeadboltStatusAPI, LoadcellStatusAPI, CameraStatusAPI, EdgePCStatusAPI };