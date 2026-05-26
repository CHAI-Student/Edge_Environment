require("dotenv").config();
const axios = require("axios");
const config = require("../../config/key");
const express = require("express");
const router = express.Router();
const { CardTerminalStatusAPI, DeadboltStatusAPI, LoadcellStatusAPI, CameraStatusAPI } = require('../Mqtt/HealthMqtt')
const { ProductList } = require("./ProductList");
const fs = require("fs");
const path = require("path");
const { callApiToControlDeadbolt } = require('../Mqtt/DeadboltApiService');
const { getProcessing, setProcessing } = require("./PaymentProcessing");
const { EventSource } = require('eventsource');
const { sendToPNT } = require("./PaymentStore");
const { ModelBrunchCheck } = require("./ModelBrunchCheck");
const { exec } = require("child_process");
const os = require("os");

const { v4: uuidv4 } = require("uuid");

function formatIfDate(d = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
       + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

const closedStates = ["LOCK", "LOCKED", "CLOSE", "CLOSED"];

// const CARD_ERROR_CODE = {
//   SUCCESS: 1,
//   TIMEOUT: 2,
//   CANCEL: 3,
//   NOT_CONDITION: 4,
//   FORMAT_ERROR: 5,
//   CAT_RUNNING: 6,
//   ERROR_RF: 7,
//   ERROR_VAN: 8,
//   ERROR_POS: 9,
//   NETWORK_ERROR: 10,
//   ERROR: 11,
// };

// function getCardErrorPubCode(error) {
//   const code =
//     error?.response?.data?.code ||
//     error?.response?.data?.response_code ||
//     error?.response?.data?.status ||
//     error?.code;

//   switch (code) {
//     case "0x00": return CARD_ERROR_CODE.SUCCESS;
//     case "0xB0": return CARD_ERROR_CODE.TIMEOUT;
//     case "0xB1": return CARD_ERROR_CODE.CANCEL;
//     case "0xB2": return CARD_ERROR_CODE.NOT_CONDITION;
//     case "0xB3": return CARD_ERROR_CODE.FORMAT_ERROR;
//     case "0xB4": return CARD_ERROR_CODE.CAT_RUNNING;
//     case "0xB5": return CARD_ERROR_CODE.ERROR_RF;
//     case "0xB6": return CARD_ERROR_CODE.ERROR_VAN;
//     case "0xC0": return CARD_ERROR_CODE.ERROR_POS;
//     case "0xC1":
//     case "ECONNABORTED":
//     case "ENOTFOUND":
//     case "ECONNREFUSED":
//       return CARD_ERROR_CODE.NETWORK_ERROR;
//     case "0xFF":
//     default:
//       return CARD_ERROR_CODE.ERROR;
//   }
// }

async function sendCardErrorToPNT(errorCode, token, CardMethod, state = "1") {
  try {
    const external = axios.create({
      baseURL: config.restApi,
      timeout: 10000,
    });

    const payload = {
      HEADER: {
        IF_ID: "IF_08",
        IF_SYSID: uuidv4(),
        IF_HOST: "CRKPNTCHAI",
        IF_DATE: formatIfDate(),
      },
      DATA: {
        device_idx: config.deviceIdx,
        division_idx: config.divisionIdx,
        token_id: token,
        payment_at: formatIfDate(),
        approve_at: '000000',
        approve_type: CardMethod === "R" ? "2" : CardMethod === "S" ? "1" : "0",
        approve_result: Number(errorCode),
        approve_price: 0,
        approve_no: "",
        approve_card_issuer: "",
        approve_card_num: "",
        approve_card_json: JSON.stringify({
          error_code: String(errorCode),
        }),
        provider: "chai",
        state, 
        result_cd: 'F',
        result_msg: 'Failed in Card Terminal'
      }
    };

    const jwtToken = config.jwtToken;

    console.log("[EDGE->PNT] CARD ERROR PAYLOAD", payload);

    const response = await external.post(
      "/chai/payment/store",
      payload,
      {
        headers: {
          Authorization: `Bearer ${jwtToken}`,
          "Content-Type": "application/json",
        },
        timeout: 30000,
      }
    );

    console.log("[PNT] Card error sent:", response.data);
    return true;
  } catch (err) {
    console.error("[PNT] Card error send failed:", err.response?.data || err.message);
    return false;
  }
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function playMp3(filePath) {
  const platform = os.platform(); // 'darwin', 'linux', 'win32'
  let cmd;
  // macOS
  if (platform === "darwin") {cmd = `afplay "${filePath}"`;}
  else if (platform === "linux") {cmd = `mpg123 "${filePath}"`;}
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

// 1분 이상 문 열림 시 음성 출력
function playDoorOpenVoice() {
    const audioPath = path.resolve(__dirname, '../Sounds/door_open.mp3');
    playMp3(audioPath);
    console.log("[VOICE] Door is still open over 1 minute. (play audio)");
}

// 
function playDeviceRunningVoice() {
    const audioPath = path.resolve(__dirname, '../Sounds/device_is_running.mp3');
    playMp3(audioPath);
    // console.log("[VOICE] Door is still open over 1 minute. (play audio)");
}

let graceTimer = null;   // 1분 후 시작용 (setTimeout)
let repeatTimer = null;  // 1분마다 반복용 (setInterval)
let startedAt = null;

function stopDoorOpenMonitor(reason = "") {
  if (graceTimer) clearTimeout(graceTimer);
  if (repeatTimer) clearInterval(repeatTimer);

  graceTimer = null;
  repeatTimer = null;
  startedAt = null;

  if (reason) console.log("[DOOR] monitor stopped:", reason);
}

function startDoorOpenMonitor(openedAt = Date.now()) {
  // 중복 방지 (OPEN이 연속 호출될 수 있으니)
  stopDoorOpenMonitor("restart");
  startedAt = openedAt;

  console.log("[DOOR] monitor started at", new Date(openedAt).toISOString());

  // 1분 뒤부터 알람 시작
  graceTimer = setTimeout(() => {
    playDoorOpenVoice(); // 1분 경과 시 즉시 1회
    repeatTimer = setInterval(playDoorOpenVoice, 60_000); // 이후 1분마다
  }, 60_000);
}

function makeTimestampFolderName(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
}

function MakeCameraFolder() {
//   if (!localRoot) throw new Error("localRoot is required");
  const folderName = makeTimestampFolderName();
//   const folderPath = path.join(localRoot, folderName);
  const folderPath = path.join(process.cwd(), `${folderName}`)
  fs.mkdirSync(folderPath, { recursive: true });
  return { folderName, folderPath };
}


// let stopPolling = true;

async function modelPooling(productData, opts = {}) {
  const { intervalMs = 10_000, timeoutMs = 5 * 60_000, checkOnly = false } = opts;
  const started = Date.now();

  /**
   * class MultiZoneRequest(BaseModel):
    """Multi-Zone 판단 요청."""

    session_id: str = Field(..., description="세션 ID (zone_{zone}_{YYMMDD}_{HHMMSS})")
    products: List[ProductInfo] = Field(
        default_factory=list,
        description="상품 목록 (선택, 무게 검증용)",
    )
   */

  // while (true) {
  //   if (Date.now() - started > timeoutMs) throw new Error("Model inference timeout");
  //   // console.log('product list', productData)

  //   try {
  //     const res = await axios.post(`${config.modelApi}/api/judge/multi-zone`, productData, { timeout: 30_000 });
  //     const data = res.data;
  //     console.log('[MODEL-RESPONSE]', data)

  //     if (data.success === true) {
  //       return data;
  //     }
  //   } catch (error) {
  //     if (error.response && error.response.status === 400) {
  //       // 4. 통신 에러/예외 발생 시: 에러 로그 찍고 null 반환하여 종료
  //       console.error("[Model] Request failed (Network/System):", e?.message || e);
  //       return;
  //     }
  //   }
  //   await delay(intervalMs);
  // }


  // [모드 1] 검증 모드 (checkOnly: true)
  // 문 열기 전에 1번만 실행해서 400 에러인지 확인하는 용도
  if (checkOnly) {
      try {
          console.log("[Validation] Checking model server status...");
          // 타임아웃을 짧게(3초) 설정해 빠르게 확인
          const res = await axios.post(`${config.modelApi}/api/judge/multi-zone`, productData, { timeout: 3000 });
          
          if (res.data.status === 400) {
              throw new Error("400 Bad Request");
          }
          return true; // 통과
      } catch (error) {
          // 400 에러면 명확하게 에러 던짐
          if (error.response && error.response.status === 400) {
              throw new Error("BLOCK_400");
          }
          // 통신 에러 등은 일단 경고만 하고 통과시킬지, 막을지 정책 결정 (여기선 false 리턴)
          console.warn("[Validation] Network Error (Ignored):", error.message);
          return false; 
      }
  }

  // [모드 2] 반복 추론 모드 (기존 로직)
  while (true) {
    if (Date.now() - started > timeoutMs) throw new Error("Model inference timeout");

    try {
      const res = await axios.post(`${config.modelApi}/api/judge/multi-zone`, productData, { timeout: 30_000 });
      const data = res.data;
      // console.log('[MODEL-RESPONSE]', data);

      if (data.success === true) {
        return data;
      }
      // 반복 중 400이 뜨면 중단
      if (data.status === 400) { 
           throw new Error("Model rejected request (Status 400)");
      }
    } catch (e) {
      console.error("[Model] Request failed (Network/System):", e?.message || e);
      // 반복 중 에러 발생 시 재시도하거나 종료 (여기선 에러 로그만 찍고 재시도)
    }
    await delay(intervalMs);
  }
}


async function requestTopCameraON({ save_path }) {
  try {
    // const CameraSaveDirApi =  `${config.cameraApi}/recording/start`;
    const request = await axios.post(`${config.cameraApi}/recording/start`, { save_path: save_path });
    // 성공 시 응답 데이터 반환
    if (request.status === 200) {
        console.log("Recording Started with Path:", request.data);
        return request.data;
    }
  } catch (error) {
    if (error.response) {
      console.error(`API Error (requestTopCameraON):`, error.response.data);
    } else {
      console.error(`Request Error (requestTopCameraON):`, error.message);
    }
    return false;
  }
}

async function requestCameraOFF() {
  try {
    // const CameraStopApi =  `${config.cameraApi}/recording/stop`;
    // await delay(5000);
    await delay(5000);
    const response = await axios.post(`${config.cameraApi}/recording/stop`);
    if (response && response.status === 200) {;
      return response.data; // 저장된 파일 경로 정보 반환 
    } else {
      console.error("Stop Recording Unexpected Response:", response && response.data);
      return false;
    }
  } catch (error) {
    if (error.response) {
      console.error("Stop Recording API Error:", error.response.data);
    } else {
      console.error("Stop Recording Request Error:", error.message);
    }
    return false;
  }
}


function waitForDeadboltClose() {
    return new Promise((resolve, reject) => {
        // [수정] 문서에 명시된 SSE 스트림 엔드포인트 사용
        const deadboltSource = new EventSource(`${config.ioboardApi}/sse?streams=doors`);

        const statusHandler = (event) => {
            if (!event.data) return;
            try {
                const data = JSON.parse(event.data);
                const currentState = data.deadbolt ? data.deadbolt.toUpperCase() : "";
                console.log(`Current Deadbolt State: ${currentState}`)
                
                if (closedStates.includes(currentState)) { 
                    deadboltSource.close(); // 리스너 해제 및 연결 종료
                    resolve({ 
                        state: currentState, 
                    });
                }
            } catch (err) {
                console.error("[Door] Event parsing error:", err);
            }
        };

        deadboltSource.addEventListener('door.update', statusHandler);

        deadboltSource.onerror = (err) => {
            console.error("[Door] SSE Error:", err);
            deadboltSource.close();
            reject(new Error("SSE connection error"));
        };
    });
}


// 전역 변수 초기화 함수 (데이터 오염 방지)
function resetGlobalTokens() {
    paymentToken = null;
    samsungpayToken = null;
    rfidToken = null;
    preAmount = null;
    preAuthNum = null;
    preAuthDate = null;
    CardMethod = null;
    paymentResponse = null;
    inferenceResult = null;
}


// let paymentToken = null
// let samsungpayToken = null
// let rfidToken = null

// let preAmount = null;
// let preAuthNum = null;
// let preAuthDate = null;
// let CardMethod = null;

let isProcessing = false;

// 카드 삽입 -- 결제 기능 시작
async function init() {
    // --- 1. 이벤트 리스너 설정 ---
    const TokenHandler = new EventSource(`${config.cardTerminalApi}/sse`);
    console.log("[Card Terminal] Listening for card tokens...");

    // 일반 카드 토큰 수신
    TokenHandler.addEventListener('tx_token_generate', (event) => {
        // e {"status": "Y", "vankey_hash": "0027057596824048aafeea42", "card_info": {"SERIAL_NUMBER": "", "ACQUIRER_ID": "003", "ACQUIRER_NAME": "\ud558\ub098\uce74\ub4dc", "ISSUER_ID": "003", "ISSUER_NAME": "\ud1a0\uc2a4\ubc45\ud06c\uce74\ub4dc", "MERCHANT_ID": "00915100663"}, "response_code": 0, "message": ""}
        try {
            const payload = JSON.parse(event.data);
            console.log('e', payload)
            paymentToken = payload.vankey_hash;
            // const CardMethod = token.startsWith("SPAYKEY") ? "S" : "N"
            CardMethod = 'N'
            // S = 삼성페이, N = 일반카드
            console.log('[CardToken] Token received:', paymentToken);
            
            // 토큰을 받으면 프로세스 시작 (비동기 호출)
            startProcess(paymentToken, CardMethod); 
        } catch (err) {
            console.error('[CardToken] Error parsing token:', err);
        }
    });

    /**
     {
        "amount": "000005000",
        "authorization_type": "PURCHASE",
        "display_message": "삼성페이 결제"
    }
     */
    // 삼성페이 토큰 수신
    TokenHandler.addEventListener('samsung_pay_init', (event) => {
        console.log('samsungpay::::', event.data); // {} -> 처음 태그 시
        if (event.data) {
            axios.post(`${config.cardTerminalApi}/payment/samsung-pay/approve`, {
                amount: "5",
                authorization_type: "PRE_AUTH", // 후결제: PURCHASE
                items: null,
                // display_message: "SamsungPay Payment"
            }).then((response) => {
                console.log('Samsung Pay Approval Response:', response.data);
                
                if (response.data.status == 'Y') {
                    preAuthNum = response.data.authorization_number;
                    preAuthDate = response.data.authorization_date;
                    samsungpayToken = response.data.vankey;
                    preAmount = '5';
                    CardMethod = 'S'
                    console.log('[Samsungpay-Token] Token received:', samsungpayToken);
                    startProcess(samsungpayToken, CardMethod); 
                }
            }).catch((error) => {
                console.error('Samsung Pay Approval Error:', error);
            });
        } 
    });

    // rfid:::: {"data": "1763193013"}
    // 사원증 토큰 수신
    TokenHandler.addEventListener('rfid_init', async (event) => {
      try {
        const checkRFID = await ModelBrunchCheck({
          division_idx: config.divisionIdx,
          device_idx: config.deviceIdx || null,
          productIdx: null,
        });
        console.log('checkRFID.DATA ======>', checkRFID.DATA)
        const paymentType = checkRFID.DATA.device_list[0].payment_type;
        console.log('paymentType ======>', paymentType);
        if (paymentType == 'POINT') {
          const payload = JSON.parse(event.data);
          console.log('rfid::::', payload); // {"data": "1763193013"}
          const token = config.jwtToken
          if (payload.data) {
              // PNT한테 사원증 토큰 전송 후 유효성 검사하기
              rfidToken = payload.data;
              CardMethod = 'R' // R = RFID
              console.log('[RFID-Token] Token received:', rfidToken);
              await axios.get(`${config.restApi}/employee-uid/validate/${rfidToken}/${config.divisionIdx}`, {
                headers: {
                  Authorization: `Bearer ${token}`,
                },
              })
                  .then((response) => {
                    console.log('[PAYMENT] RFID Response:', response.data);
                    if (response.data.result == '0') {
                      console.log('[RFID-Token] Token received:', response.data.message);
                      startProcess(rfidToken, CardMethod); 
                    } else {
                      console.log('[RFID-Token] Token received:', response.data.message);
                    }
                  })
          }
        } else {
          console.log('[RFID-Token] This is not RFID Device');
        }
      } catch (error) {
        console.error('RFID Approval Error:', error);
      }
    });
}

// --- 2. 프로세스 시작 및 상태 체크 ---
async function startProcess(token, CardMethod) {
    // [수정] 1. 프로세스가 이미 실행 중이면 요청 무시 (Busy Check)
    if (getProcessing()) {
        console.warn('[SYSTEM] Device is busy. Ignoring new request');
        // 필요 시 사용자에게 "사용 중입니다" 음성 안내 추가 가능
        playDeviceRunningVoice()
        return; 
    }
    // [수정] 2. 프로세스 잠금 (Lock)
    // isProcessing = true;
    setProcessing(true);
    try {
      const CameraStatus = await CameraStatusAPI()
      // const CardTerminalStatus = await CardTerminalStatusAPI()
      const CardTerminalStatus = '39'
      const DeadboltStatus = await DeadboltStatusAPI()
      const LoadcellStatus = await LoadcellStatusAPI()

      if (CardTerminalStatus == '39' && DeadboltStatus == '19' && LoadcellStatus == '29' && CameraStatus == '09') {
          console.log('[PAYMENT] Health check passed. Starting Payments process...');
          try {
              await Payments(token, CardMethod);
          } catch (error) {
              console.error("[PAYMENT] Process failed:", error);
          }
      } else {
          console.error('[PAYMENT] Health status is bad. Cannot run.');
          return;
      }
    } catch (error) {
        console.error("[PAYMENT] Process failed:", error);
      } finally {
          // [수정] 3. 프로세스 잠금 해제 (Unlock)
          // 성공하든 실패하든 반드시 실행되어야 함.
          // isProcessing = false;
          setProcessing(false);
          
          // [권장] 다음 결제를 위해 전역 토큰 변수 초기화
          resetGlobalTokens(); 
          
          console.log("[SYSTEM] Process finished. Ready for next user.");
      }
}

// let LoadcellData = null
let paymentResponse = null;
let inferenceResult = null;

// --- 3. 결제 및 제어 로직 ---
async function Payments(token, CardMethod) {
    const divisionIdx = config.divisionIdx;

    // [3] 상품정보 조회
    const productList = await ProductList({
        division_idx: divisionIdx,
        device_idx: null
    });
    // console.log("[ProductList] Data Loading Complete:", productList);


    // 상품 정보 추출
    let productData = []
    if (productList) { productData = productList.DATA.product_list }
    // console.log(productData)
    // 2. API 스펙(ProductInfo)에 맞춰 매핑 (Mapping)
    const formattedProducts = productData.map((item) => {
      return {
        product_idx: item.product_idx,      // 매칭: P17355176366172772
        product_name: item.product_eng_name,    // 매칭: 광동) 제주 삼다수 500ml
        sale_price: parseInt(item.sale_price),        // 매칭: 1500 (Integer)
        product_weight: item.product_loadcell_weight, // 매칭: '530' (String, API 정의와 일치)
        has_loadcell: item.has_loadcell == 'Y' ? "true" : item.has_loadcell == 'N' ? "false" : 'null',
        stock_qty: parseInt(item.stock_qty)
      };
    });

    // 3. 최종 전송 데이터 구성 (MultiZoneRequest)
    const requestPayload = {
      session_id: 'OPEN',
      products: formattedProducts
    };

    try {
        // checkOnly: true 옵션을 줘서 1번만 찔러봄
        await modelPooling(requestPayload, { checkOnly: true });
        console.log("[Validation] Model server success");
    } catch (error) {
        if (error.message === "BLOCK_400") {
            console.error("[BLOCK] Model server access denined");
            return; // 여기서 함수 완전 종료 -> 문 안 열림
        }
        console.log("Validation Warning:", error.message);
    }
  
    // [4] 카메라 폴더 생성
    // const LOCAL_ROOT = path.resolve(process.cwd()); 
    const { folderName, folderPath } = MakeCameraFolder();
    console.log("[Camera] Folder Created:", folderPath, 'name:', folderName);

    // [5] 문 열기 (OPEN)
    const openResult = await callApiToControlDeadbolt("OPEN");
    if (openResult !== "OPEN" && openResult !== 'UNLOCK') throw new Error(`Failed to open door. Status: ${openResult}`) 

    // 모델 서버 요청 (POST)
    // console.log("[Model] Sending data for inference...", requestPayload);
    // stopPolling = false;
    const inferencePromise = modelPooling(requestPayload, { intervalMs: 10_000 });
    // if (inferencePromise == null) return;

    // 문 열림 알림 시작 - 1분간
    startDoorOpenMonitor(Date.now());
    
    // // 상품 정보 추출
    // let productData = []
    // let closeEventData = ''
    // if (productList) { productData = productList.DATA.product_list }
    // // console.log(productData)
    // // 2. API 스펙(ProductInfo)에 맞춰 매핑 (Mapping)
    // const formattedProducts = productData.map((item) => {
    //   return {
    //     product_idx: item.product_idx,      // 매칭: P17355176366172772
    //     product_name: item.product_eng_name,    // 매칭: 광동) 제주 삼다수 500ml
    //     sale_price: parseInt(item.sale_price),        // 매칭: 1500 (Integer)
    //     product_weight: item.product_loadcell_weight, // 매칭: '530' (String, API 정의와 일치)
    //     has_loadcell: item.has_loadcell == 'Y' ? "true" : item.has_loadcell == 'N' ? "false" : 'null',
    //     stock_qty: item.stock_qty
    //   };
    // });

    // // 3. 최종 전송 데이터 구성 (MultiZoneRequest)
    // const requestPayload = {
    //   session_id: openResult == 'UNLOCK' ? 'OPEN' : closeEventData == 'LOCKED' ? 'CLOSE' : 'NULL',
    //   products: formattedProducts
    // };
    
    // // 모델 서버 요청 (POST)
    // console.log("[Model] Sending data for inference...", requestPayload);
    // // stopPolling = false;
    // const inferencePromise = modelPooling(requestPayload, { intervalMs: 10_000 });

    // [6] 상단 카메라 ON 요청
    await requestTopCameraON({ save_path: folderPath});

    // [7] 로드셀 무게 정보 실시간 전달
    
    // [8] 로드셀 무게 변화 감지

    // [9] 데드볼트 상태 (close) (sensor → node) + (상단 카메라 off + folder snapshot) 저장 (node → camera python)
    try {
      // 1. 문이 닫히고 로그 경로가 올 때까지 대기
      const closeEventData = await waitForDeadboltClose();
      // console.log('ddddddddddd', closeEventData)
      const state = closeEventData.state;
      if (state && closedStates.includes(state)) {
          requestPayload.session_id = 'CLOSE';
          // stopPolling = true;
          stopDoorOpenMonitor("deadbolt closed");
          console.log("[DEADBOLT] Door closed detected:", closeEventData.state);
        try {
          await axios.post(`${config.ioboardApi}/recording/stop`, {}); 
          await delay(5000);
          // console.log("녹화 종료 성공");
        } catch (error) {
          // console.error("녹화 종료 실패:", error);
        }
        try {
          await requestCameraOFF();
        } catch (e) {
          console.error("[CAM] OFF failed:", e?.message || e);
        }
      } else {
        console.log("[DEADBOLT] Close event received but state not closed:", state);
      }
    } catch (error) {
        console.error("[Process Error] Door/Camera Sequence:", error);
        return; // 에러 시 중단
    }

    // 로드셀 무게 log 불러오기
    // try {
    //       const resp = await axios.get(`${config.ioboardApi}/recording/data`, {});
    //       // Use only the data payload (avoid passing axios response object which contains circular refs)
    //       LoadcellData = resp.data;
    //       // console.log('[LoadcellData]', LoadcellData.logs, { depth: null })
    //       console.log('[LoadcellData] loadcell data responsed')
    //     } catch (error) {
    //       if (error.response) {
    //         console.error("로드셀 데이터 갖고오기 실패:", error.response.data);
    //       } else {
    //         console.error("로드셀 데이터 갖고오기 실패:", error.message);
    //       }
    //     } // 여기까지는 확인 완료 --> 0129
    // [10] 모델 서버에 상품 목록 + 카메라 폴더명 + 로드셀 데이터 전송 → 추론 결과 수신
    // [10] 모델 서버에 상품 목록 → 추론 결과 수신
    // [Model] request failed: Request failed with status code 422
    // product_idx 기준 map 생성
    const productMap = new Map(
        productData.map(p => [
            String(p.product_idx),
            p
        ])
    );

    try {
        inferenceResult = await inferencePromise;
        console.log("[Model] Inference Result:", inferenceResult);
        console.log('card method', CardMethod)
        // stopPolling = true;
        if (inferenceResult.success == false || inferenceResult.status == 'error'){
          console.error("[PAYMENT] Model inference failed or error occurred. Process aborted.");
          return;
        }
        if (inferenceResult.success == true && inferenceResult.totalPrice == 0) {
          // 0원일 때 선결제 취소되게 하기
          if (CardMethod === "S") {
            await axios.post(`${config.cardTerminalApi}/payment/samsung-pay/cancel`,{
                amount: preAmount,
                original_authorization_date: preAuthDate,
                original_authorization_number: preAuthNum,
                vankey: samsungpayToken
            }).then((response) => {
              console.log('canceled samsung-pay : ', response.data)
            })
          }
          console.log('total price is 0, running end')
          return;
        }
        if (inferenceResult.success == true && inferenceResult.products){
          // 결제 승인 요청
          const finalAmount = inferenceResult.totalPrice;
          // console.log('inferenceResult', inferenceResult)
          const products = inferenceResult.products
          // const items = products.map(product => ({
          //   name: product.name.slice(0, 5),
          //   quantity: Number(product.count),
          //   total_price: Number(product.price) * Number(product.count || 1)
          // }));
          const items = products.map(product => {
            const master = productMap.get(String(product.productIdx));
            if (!master) {
                console.warn(
                    `[PNT] Product master not found: productIdx=${product.productIdx}`
                );
            }
            return {
                name: (master.product_name || product.name || "").slice(0, 5),
                quantity: Number(product.count),
                total_price: Number(product.price) * Number(product.count || 1)
            };
          });
          // 삼성 페이
          if (CardMethod === "S") {
            // paymentResponse = await axios.post(`${config.cardTerminalApi}/payment/samsung-pay/approve`, {
            //         // amount: string(finalAmount),
            //         amount: '5',
            //         authorization_type: "PURCHASE",
            //         items,
            //         // display_message: "SamsungPay Payment"
            // });
            try {
              paymentResponse = await axios.post(
                `${config.cardTerminalApi}/payment/samsung-pay/approve`,
                {
                  // amount: string(finalAmount),
                  amount: '5',
                  items,
                  authorization_type: "PURCHASE",
                },
                {
                  timeout: 60000
                }
              );
            } catch (error) {
              const pubCode = '1'

              await sendCardErrorToPNT(
                pubCode,
                token,
                CardMethod,
                "2"
              );

              return;
            }
            await axios.post(`${config.cardTerminalApi}/payment/samsung-pay/cancel`,{
                amount: preAmount,
                original_authorization_date: preAuthDate,
                original_authorization_number: preAuthNum,
                vankey: samsungpayToken
            }).then((response) => {
              console.log('canceled samsung-pay : ', response.data)
            })
          }
          // 일반 카드
          else if (CardMethod === "N"){
            // paymentResponse = await axios.post(`${config.cardTerminalApi}/payment/token/approve`, {
            //         // amount: String(finalAmount),
            //         amount: '5',
            //         items,
            //         vankey_hash: String(paymentToken || token)
            // });
            try {
              paymentResponse = await axios.post(
                `${config.cardTerminalApi}/payment/token/approve`,
                {
                  // amount: string(finalAmount),
                  amount: '5',
                  items,
                  vankey_hash: String(paymentToken || token)
                }
              );
            } catch (error) {
              const pubCode = '1';

              await sendCardErrorToPNT(
                pubCode,
                token,
                CardMethod
              );

              console.error(
                "[CARD] Approval failed:",
                pubCode,
                error.response?.data || error.message
              );

              return;
            }
          }
          // RFID 사원증
          else if (CardMethod === "R"){
            paymentResponse = {
                    // amount: String(finalAmount),
                    amount: '5',
                    items
            };
          }
          else {  
            console.log("Undefined Card Method Detected.")
            return;
          }
          // 결제 결과 처리
          if (paymentResponse && paymentResponse.status === 200) {
              // const paymentAt = new Date()
              // 형식: "payment_at": "2026-02-21T00:46:59.000",
              const paymentAt = new Date().toISOString().replace("Z", "");
              console.log("[PAYMENT] Success:", paymentResponse.data, token);
              
              await sendToPNT(
                paymentResponse.data,
                inferenceResult,
                folderPath,
                paymentAt,
                CardMethod,
                productData,
                token
              )
          } else if (paymentResponse && CardMethod === "R") {
            // RFID 결제 정보 전송
            const paymentAt = new Date().toISOString().replace("Z", "");
            console.log("[PAYMENT] Success:", paymentResponse);
            await sendToPNT(
              paymentResponse,
              inferenceResult,
              folderPath,
              paymentAt,
              CardMethod,
              productData,
              token
            )
          } else {
              console.error("[PAYMENT] Failed:", paymentResponse.data);

          }
        } else {
          console.log('inferenceResult not found')
        }
    } catch (error) {
        console.error("[MODEL/PAYMENT] Inference Request Failed:", error.message);
        return;
    } 
    // finally {
    //     isProcessing = false;
    //     resetGlobalTokens(); 
        
    //     console.log("[SYSTEM] Process finished. Ready for next user.");
    // }
}

module.exports = { Payments, router, init };