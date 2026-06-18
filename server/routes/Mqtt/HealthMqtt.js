const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const axios = require("axios"); // ✅ API 통신을 위한 라이브러리
const { devAutoLogin } = require("../../routes/auth");
const { exec } = require("child_process");
const os = require("os");
const path = require("path");
const fs = require("fs");

function formatIfDate(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}`
         + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function playMp3(filePath) {
  const platform = os.platform(); // 'darwin', 'linux', 'win32'
  let cmd;
  // macOS
  if (platform === "darwin") {cmd = `afplay "${filePath}"`;}
  else if (platform === "linux") {
    cmd = `mpg123 -f 32768 "${filePath}"`; // 100%
  }
  else {
    console.warn("[AUDIO] Unsupported OS:", platform);
    return;
  }
  exec(cmd, (err) => {
    if (err) {
      console.error("[AUDIO] play failed:", err.message);
    }
  });
}

let sensorErrorVoiceInterval = null;

function playSensorErrorVoice() {
    const audioPath = path.resolve(__dirname, '../Sounds/sensor_error.mp3');
    playMp3(audioPath);
    console.log("[VOICE] sensor error. (play audio)");
}

async function DiskStatusAPI() {
  return new Promise((resolve) => {
    // sd카드 루트 저장 공간 체크 : /dev/nvme0n1p2
    exec("df -h /", (error, stdout, stderr) => {
      if (error) {
        console.error(`[DISK] command error: ${error.message}`);
        return resolve("40"); // 디스크 체크 실패
      }
      if (stderr) {
        console.error(`[DISK] stderr: ${stderr}`);
        return resolve("40");
      }
      const lines = stdout.trim().split("\n");
      if (lines.length < 2) return resolve("40");

      const infoLine = lines[1].replace(/\s+/g, " ");
      const usePercentageStr = infoLine.split(" ")[4];
      const usePercentage = parseInt(usePercentageStr.replace("%", ""), 10);

      if (Number.isNaN(usePercentage)) return resolve("40");

      // 80% 이상 시 저장공간 부족 띄우기
      if (usePercentage >= 99) {
        console.error(`[DISK] Not enough disk space. usage=${usePercentage}%`);
        return resolve("40"); // 디스크 부족
      }
      console.log(`[DISK] OK. usage=${usePercentage}%`);
      return resolve("49"); // 정상
    });
  });
}

let CardErrorState = null;

function CardTerminalErrorState(code) {
  CardErrorState = code;
  console.log("[CARD-HEALTH] set:", code);
}

async function CardTerminalStatusAPI(CatResCodePayment) {
  let CardTerminalState = '30'
  // console.log(`[CARD-DEVICE] test:: ${config.cardTerminalApi}`);
  try {
    console.log(`[CARD-DEVICE] Sending Request to ${config.cardTerminalApi}`);

    if (CatResCodePayment == "178") { // payment에서 보내는 단말기 에러
      switch (String(CatResCodePayment)) {
        case "176": return "32";
        case "177": return "33";
        case "178": return "34";
        case "179": return "35";
        case "180": return "36";
        case "181": return "37";
        case "182": return "31";
        case "192": return "30";
        case "193": return "30";
        case "194": return "39";
        case "255": return "38";
      }
    }

    // POST 요청 전송
    const response = await axios.get(`${config.cardTerminalApi}/status`, {
      timeout: 30000 // 30초 안에 응답 없으면 에러 처리

    });
    console.log('[CARD-DEVICE]', response.data)

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
    } else if (CatResCode == "192" || CatResCode == "193" || CatStatus == 'ERROR_POS' || CatStatus == 'NETWORK_ERROR') { 
      // 카드 단말기 통신 불량
      CardTerminalState = '30'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "255" || CatStatus == 'ERROR') { // 기타 오류
      CardTerminalState = '38'
      // console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (response.data.status == 504) { // timeout error
      CardTerminalState = '30'
      console.log(`[CARD-DEVICE]: ${CardTerminalState} / ${CatStatus}`);
    } else if (CatResCode == "194" || CatStatus == "NOCHK_NETWORK") {
      // ping 설정 안 한 거 --> 에러 아님
      CardTerminalState = '39'
    }return CardTerminalState
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

let DeadboltErrorState = null;

function DeadboltTerminalErrorState(code) {
  DeadboltErrorState = code;
  console.log("[DEADBOLT-HEALTH] set:", code);
}

async function DeadboltStatusAPI() {
  // deadbolt status check
  let DeadboltState = '10'
  try {
    console.log(`[IO-BOARD/DEADBOLT] Sending Request to ${config.ioboardApi}`);
    IOBoardRes = await axios.get(`${config.ioboardApi}/health`, { timeout: 5000 });
    console.log(IOBoardRes.data)
    if (IOBoardRes.data.door !== 'HEALTHY') {
      // 3분 이상 문이 열려있는 경우
      DeadboltState = '12';
    } else if (IOBoardRes.data.deadbolt == 'HEALTHY') {
      DeadboltState = '19';
    } else {
      // 연결 불량이거나 도어와 데드볼트 상태가 상이할 때
      DeadboltState = '10';
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
  let LoadcellState = '20'
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
  let CameraState = '00'
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
  let edgeStatus = '40';
  let ModelRes = null;
  let aiServercheck = null;

  try {
    // console.log(`[NETWORK] Network status`);

    // 1. ai server health-check
    console.log(`[AI SERVER-EDGEPC] Sending Request to ${config.aiServerApi}`);
    aiServercheck = await axios.get(`${config.aiServerApi}/health`, { timeout: 5000 });
    console.log('[AI SERVER] AIServerCheck:', aiServercheck.data);
    const AiServerState = aiServercheck.data.ok

    // 2. 모델 서버 상태 확인
    console.log(`[MODEL-EDGEPC] Sending Request to ${config.modelApi}`);
    ModelRes = await axios.get(`${config.modelApi}/api/health`, { timeout: 5000 });
    console.log('[MODEL] ModelRes:', ModelRes.data);

    const DiskStatus = await DiskStatusAPI();

    // 3. 상태 판단
    if (DiskStatus == "40") {
      edgeStatus = "40";
      console.log('[DiskStatus] :', edgeStatus, '---', DiskStatus);
    } else if (LoadcellState == '29' && DeadboltState == '19' && ModelRes.data.status && AiServerState == true) {
      // console.log('[EDGEPC] All systems healthy')
      edgeStatus = '49'
    } else if (LoadcellState != '29' && DeadboltState != '19') {
      edgeStatus = '41'
      // console.log('[EDGEPC] IO Board unconnected')
    } else if (aiServercheck.data.ok == false) {
      edgeStatus = '43'
    }
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


  const client = getClient(); // 연결 시작
  client.on("connect", () => {
    console.log("[MQTT] connected");
    // const CameraStatus = "09";
    // const DeadboltStatus = '19'
    // const LoadcellStatus = '29'
    // const CardTerminalStatus = '39'

    const publishOnce = async () => {
      let CardTerminalStatus = await CardTerminalStatusAPI();
      if (CardErrorState) {
        CardTerminalStatus = CardErrorState;
        CardErrorState = null; // 여기서 1회 전송 후 초기화
      }
      // const CardTerminalStatus = '39'
      let DeadboltStatus = await DeadboltStatusAPI();
      if (DeadboltErrorState) {
        DeadboltStatus = DeadboltErrorState;
        DeadboltErrorState = null; // 1회 전송 후 초기화
      }
      const LoadcellStatus = await LoadcellStatusAPI();
      const CameraStatus = await CameraStatusAPI();
      const EdgePCStatus = await EdgePCStatusAPI(DeadboltStatus, LoadcellStatus);

      // 센서 에러나면 20초에 한번씩 소리 나게
      if (CardTerminalStatus == '30' || LoadcellStatus == '20' || CameraStatus == '00') {
        if (!sensorErrorVoiceInterval) {
          playSensorErrorVoice();
          sensorErrorVoiceInterval = setInterval(() => {
            playSensorErrorVoice();
          }, 30000);
        }
      } else {
        if (sensorErrorVoiceInterval) {
          clearInterval(sensorErrorVoiceInterval);
          sensorErrorVoiceInterval = null;
        }
      }

      const header = {
        IF_ID: "IF_02",
        IF_SYSID: uuidv4(),
        IF_HOST: "CRKPNTCHAI",
        IF_DATE: formatIfDate(),
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

module.exports = { HealthMqtt, CardTerminalStatusAPI, DeadboltStatusAPI, LoadcellStatusAPI, CameraStatusAPI, EdgePCStatusAPI, CardTerminalErrorState, DeadboltTerminalErrorState };