require("dotenv").config();
const axios = require("axios");
const config = require("../../config/key");
const express = require("express");
const router = express.Router();
const { CardTerminalStatusAPI, DeadboltStatusAPI, LoadcellStatusAPI, CameraStatusAPI } = require('../Mqtt/HealthMqtt')
const { ProductList } = require("./ProductList");
const fs = require("fs");
const path = require("path");
const { callApiToControlDeadbolt } = require('../Mqtt/DeadboltApiService'); // [추가] 도어 제어 함수 임포트 가정
const { EventSource } = require('eventsource');
const { sendToPNT } = require("./PaymentStore");
const { exec } = require("child_process");
const os = require("os");

const closedStates = ["LOCK", "LOCKED", "CLOSE", "CLOSED"];

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

// 🔊 실제 음성 출력 함수로 교체
function playDoorOpenVoice() {
    const audioPath = path.resolve(__dirname, '../Sounds/door_open.mp3');
    playMp3(audioPath);
    console.log("[VOICE] Door is still open over 1 minute. (play audio)");
}

const CHECK_INTERVAL_MS = 3000;   // 상태 확인 주기
const GRACE_MS = 60_000;          // 1분 지난 뒤부터
const REPEAT_MS = 60_000;         // 1분마다 반복

let doorOpenStartedAt = null;
let checkTimer = null;
let voiceTimer = null;

function startDoorOpenMonitor() {
  stopDoorOpenMonitor("restart");
  console.log("[DOOR] Door-open monitor started");

  checkTimer = setInterval(async () => {
    try {
        const { DeadboltState, DeadboltOpen } = await DeadboltStatusAPI();
        const open = DeadboltOpen === 'HEALTHY';

      if (open) {
        // 첫 OPEN 감지 시각 기록
        if (!doorOpenStartedAt) {
          doorOpenStartedAt = Date.now();
          console.log("[DOOR] openedAt =", new Date(doorOpenStartedAt).toISOString());
        }

        const elapsed = Date.now() - doorOpenStartedAt;

        // 1분 경과 후 음성 반복 시작 (딱 1번만 세팅)
        if (elapsed >= GRACE_MS && !voiceTimer) {
          console.log("[DOOR] open > 60s, start voice repeating");
          playDoorOpenVoice(); // 시작 즉시 1회
          voiceTimer = setInterval(playDoorOpenVoice, REPEAT_MS);
        }
      } else {
        // 문 닫힘(또는 잠김/이상) 감지되면 모두 중단
        if (doorOpenStartedAt || voiceTimer) {
          stopDoorOpenMonitor("door closed or not healthy");
        }
      }
    } catch (e) {
      // health 체크 실패는 서버 죽이면 안 됨
      console.error("[DOOR] /health check failed:", e.message);
      // 실패 시에는 상태를 "모름"으로 두고, 기존 타이머 유지(원하면 여기서 stop도 가능)
    }
  }, CHECK_INTERVAL_MS);
}

function stopDoorOpenMonitor(reason = "") {
  if (checkTimer) clearInterval(checkTimer);
  if (voiceTimer) clearInterval(voiceTimer);

  checkTimer = null;
  voiceTimer = null;
  doorOpenStartedAt = null;

  if (reason) console.log("[DOOR] Door-open monitor stopped:", reason);
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

// async function requestTopCameraCapture({ action }) {
//   try {
//     let url;
//     if (action === 'ON') {
//       url = `${config.cameraApi}/api/zone/0/activate`; 
//       // 상단카메라 키는 함수여서 카메라 인덱스 0으로 고정
//     } else if (action === 'OFF') {
//       url = `${config.cameraApi}/api/zone/${zoneId}/deactivate`;
//     } else {
//       throw new Error("Invalid action. Use 'ON' or 'OFF'.");
//     }

//     // 2. 스냅샷 경로와 같이 요청 전송
//     const response = await axios.post(url);

//     if (response.status === 200) {
//       console.log(`Camera Zone 0 ${action} Success:`, response.data);
//       return true;
//     }

//   } catch (error) {
//     if (error.response) {
//       console.error(`API Error (${action}):`, error.response.data);
//     } else {
//       console.error(`Request Error (${action}):`, error.message);
//     }
//     return false;
//   }
// }

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

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function requestCameraOFF() {
  try {
    // const CameraStopApi =  `${config.cameraApi}/recording/stop`;
    // await delay(5000);
    const response = await axios.post(`${config.cameraApi}/recording/stop`, delay(5000));
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
    return new Promise((resolve) => {
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
        };
    });
}


let paymentToken = null
let samsungpayToken = null
let rfidToken = null

let preAmount = null;
let preAuthNum = null;
let preAuthDate = null;
let CardMethod = null;

// 카드 삽입 -- 결제 기능 시작
async function init() {
    // --- 1. 이벤트 리스너 설정 ---
    const TokenHandler = new EventSource(`${config.cardTerminalApi}/sse`);
    console.log("[Card Terminal] Listening for card tokens...");

    // 일반 카드 토큰 수신
    TokenHandler.addEventListener('tx_token_generate', (event) => {
        // e {"status": "Y", "vankey_hash": "0027057596824048aafeea42", "card_info": {"SERIAL_NUMBER": "", "ACQUIRER_ID": "003", "ACQUIRER_NAME": "\ud558\ub098\uce74\ub4dc", "ISSUER_ID": "003", "ISSUER_NAME": "\ud1a0\uc2a4\ubc45\ud06c\uce74\ub4dc", "MERCHANT_ID": "00915100663"}, "response_code": 0, "message": ""}
        console.log('e', event.data)
        if (event.data) {
            try {
                paymentToken = event.data.vankey_hash;
                // const CardMethod = token.startsWith("SPAYKEY") ? "S" : "N"
                CardMethod = 'N'
                // S = 삼성페이, N = 일반카드
                console.log('[CardToken] Token received:', paymentToken);
                
                // 토큰을 받으면 프로세스 시작 (비동기 호출)
                startProcess(paymentToken, CardMethod); 
            } catch (err) {
                console.error('[CardToken] Error parsing token:', err);
            }
        } else {
            console.log('[CardToken] No token data received');
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
                display_message: "SamsungPay Payment"
            }).then((response) => {
                console.log('Samsung Pay Approval Response:', response.data);
                if (response.status == 'Y') {
                    preAuthNum = response.data.authorization_number;
                    preAuthDate = response.data.authorization_date;
                    samsungpayToken = response.data.vankey;
                    preAmount = response.data.amount;
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
    TokenHandler.addEventListener('rfid_init', (event) => {
        console.log('rfid::::', event.data); // {"data": "1763193013"}
        if (event.data.date) {
            // PNT한테 사원증 토큰 전송 후 유효성 검사하기
            rfidToken = event.data.data;
            CardMethod = 'R' // R = RFID
            console.log('[RFID-Token] Token received:', rfidToken);
            // startProcess(rfidToken, CardMethod);
        }
    });
}

// --- 2. 프로세스 시작 및 상태 체크 ---
async function startProcess(token, CardMethod) {
    const CameraStatus = await CameraStatusAPI()
    const CardTerminalStatus = await CardTerminalStatusAPI()
    const DeadboltStatus = await DeadboltStatusAPI()
    const LoadcellStatus = await LoadcellStatusAPI()

    if (CardTerminalStatus == '39' && DeadboltStatus == '19' && LoadcellStatus == '29' && CameraStatus == '09') {
        console.log('[PAYMENT] Health check passed. Starting Payments process...');
        try {
            await Payments(CardMethod);
        } catch (error) {
            console.error("[PAYMENT] Process failed:", error);
        }
    } else {
        console.error('[PAYMENT] Health status is bad. Cannot run.');
    }
}

/**
 * 결제 취소 요청 함수
 * @param {Object} paymentResult - 결제 승인(Approve) 후 받은 응답 데이터
 * @param {string} originalToken - SSE로 받았던 초기 토큰 (vankey_hash)
 * @param {string} amount - 취소할 금액
 * @param {string} CardMethod - 'S'(삼성페이) or 'N'(일반)
 */
// async function cancelPayment(paymentResult, originalToken, amount, CardMethod) {
//     console.log(`[PAYMENT] Initiating Cancellation... Method: ${CardMethod}`);

//     try {
//         let cancelPayload = {};
//         let cancelEndpoint = "";
//         const authDate = paymentResult.authorization_date;
//         const authNum = paymentResult.authorization_number;

//         if (!authDate || !authNum) {
//             throw new Error("Cannot cancel: Missing authorization info from payment result.");
//         }

//         if (CardMethod === "S") {
//             cancelEndpoint = `${config.cardTerminalApi}/payment/samsung-pay/cancel`;
            
//             cancelPayload = {
//                 amount: amount,
//                 original_authorization_date: authDate,
//                 original_authorization_number: authNum,
//                 vankey: paymentResult.vankey
//             };

//         } else if (CardMethod === "N") {
//             cancelEndpoint = `${config.cardTerminalApi}/payment/token/cancel`;

//             cancelPayload = {
//                 amount: amount,
//                 original_authorization_date: authDate,
//                 original_authorization_number: authNum,
//                 vankey_hash: originalToken
//             };
//         } else {
//             throw new Error("Unknown Payment Method");
//         }

//         console.log(`[PAYMENT] Sending Cancel Request to ${cancelEndpoint}`, cancelPayload);

//         const response = await axios.post(cancelEndpoint, cancelPayload);

//         if (response.data && response.data.status === "ok") { // 또는 성공 코드 확인
//             console.log("[PAYMENT] Cancellation Successful:", response.data);
//             return true;
//         } else {
//             console.error("[PAYMENT] Cancellation Failed:", response.data);
//             return false;
//         }

//     } catch (error) {
//         console.error("[PAYMENT] Cancel API Error:", error.message);
//         if (error.response) {
//             console.error("Detail:", error.response.data);
//         }
//         return false;
//     }
// }


let LoadcellData = null
let paymentResponse = null;
let inferenceResult = null;

// --- 3. 결제 및 제어 로직 ---
async function Payments(CardMethod) {
    const divisionIdx = config.divisionIdx;

    // [3] 상품정보 조회
    const productData = await ProductList({
        division_idx: divisionIdx,
        device_idx: null
    });
    console.log("[ProductList] Data Loading Complete:", productData);

    // [4] 카메라 폴더 생성
    // const LOCAL_ROOT = path.resolve(process.cwd()); 
    const { folderName, folderPath } = MakeCameraFolder();
    console.log("[Camera] Folder Created:", folderPath, 'name:', folderName);

    // [5] 문 열기 (OPEN)
    const openResult = await callApiToControlDeadbolt("OPEN");
    if (openResult !== "OPEN" && openResult !== 'UNLOCK') throw new Error(`Failed to open door. Status: ${openResult}`)

    // 문 열림 알림 시작 - 1분간
    startDoorOpenMonitor();

    // [6] 상단 카메라 ON 요청
    await requestTopCameraON({ save_path: folderPath});

    // [7] 로드셀 무게 정보 실시간 전달
    
    // [8] 로드셀 무게 변화 감지

    // [9] 데드볼트 상태 (close) (sensor → node) + (상단 카메라 off + folder snapshot) 저장 (node → camera python)
    try {
        // 1. 문이 닫히고 로그 경로가 올 때까지 대기
        const closeEventData = await waitForDeadboltClose();
        try {
          await axios.post(`${config.ioboardApi}/recording/stop`, {}); 
          await delay(5000);
          console.log("녹화 종료 성공");
        } catch (error) {
          console.error("녹화 종료 실패:", error);
        }

        if (closedStates.includes(closeEventData.state)) {
            console.log("[DEADBOLT] Door closed detected:", closeEventData.state);
            await requestCameraOFF();
        }
    } catch (error) {
        console.error("[Process Error] Door/Camera Sequence:", error);
        return; // 에러 시 중단
    }

    // 로드셀 무게 log 불러오기
    try {
          const resp = await axios.get(`${config.ioboardApi}/recording/data`, {});
          // Use only the data payload (avoid passing axios response object which contains circular refs)
          LoadcellData = resp.data;
          // console.log('[LoadcellData]', LoadcellData.logs, { depth: null })
        } catch (error) {
          if (error.response) {
            console.error("로드셀 데이터 갖고오기 실패:", error.response.data);
          } else {
            console.error("로드셀 데이터 갖고오기 실패:", error.message);
          }
        } // 여기까지는 확인 완료 --> 0129
    // [10] 모델 서버에 상품 목록 + 카메라 폴더명 + 로드셀 데이터 전송 → 추론 결과 수신
    try {
        console.log("[Model] Sending data for inference...");
        // req
        const inferencePayload = {
            ProductList     : productData,
            ImageFolder     : folderPath,
            Loadcell        : LoadcellData,
        };

        // 모델 서버 요청 (POST)
        const modelRes = await axios.post(`${config.modelApi}/api/judge/multi-zone`, inferencePayload);
        // 모델이 추론 결과를 보낼때 까지 계속 10초 간격으로 post(만약 추론이 안 끝났으면 모델은 아직 안 끝났다는 response를 보내야 함.)
        setInterval(() => {modelRes}, 10000);
        if (!modelRes.data.success == true) {
            inferenceResult = modelRes.data;
            console.log("[Model] Inference Result:", inferenceResult);
        }

        // 결제 승인 요청
        const finalAmount = inferenceResult.totalPrice;
        const paymentAt = new Date()
        if (modelRes.data.success === true){
          // 삼성 페이
          if (CardMethod === "S") {
            paymentResponse = await axios.post(`${config.cardTerminalApi}/payment/samsung-pay/approve`, {
                    amount: finalAmount, 
                    authorization_type: "PURCHASE",
                    display_message: "SamsungPay Payment"
                });
            await axios.post(`${config.cardTerminalApi}/payment/samsung-pay/cancel`,{
                amount: preAmount,
                original_authorization_date: preAuthDate,
                original_authorization_number: preAuthNum,
                vankey: samsungpayToken
            })
          }
          // 일반 카드
          else if (CardMethod === "N"){
            paymentResponse = await axios.post(`${config.cardTerminalApi}/payment/token/approve`, {
                    amount: finalAmount,
                    vankey_hash: paymentToken
                });
          }
          else{
            console.log("Undefined Card Method Detected.")
            return;
          }
        }
        // 결제 결과 처리
        if (paymentResponse && paymentResponse.status === 200) {
            console.log("[PAYMENT] Success:", paymentResponse.data);
            sendToPNT(
              paymentResponse,
              inferenceResult,
              folderPath,
              paymentAt,
              CardMethod
            )

        } else {
            console.error("[PAYMENT] Failed:", paymentResponse);
        }

    } catch (error) {
        console.error("[Model] Inference Request Failed:", error.message);
    }
}

module.exports = { Payments, router, init };