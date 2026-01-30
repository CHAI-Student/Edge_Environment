require("dotenv").config();
const axios = require("axios");
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");
const { devAutoLogin } = require("../auth");
const express = require("express");
const router = express.Router();
// const { HealthMqtt } = require("../Mqtt/HealthMqtt");
const { CardTerminalStatusAPI, DeadboltStatusAPI, LoadcellStatusAPI } = require('../Mqtt/HealthMqtt')
const { ProductList } = require("./ProductList");
const fs = require("fs");
const path = require("path");
const { ManualDeadbolt } = require("../Mqtt/ManualDeadbolt");
const { callApiToControlDeadbolt } = require('../Mqtt/DeadboltApiService'); // [추가] 도어 제어 함수 임포트 가정
const { EventSource } = require('eventsource');
const { model } = require("mongoose");
const { record } = require("zod");
const { sendToPNT } = require("./PaymentStore");
const { send } = require("process");

const closedStates = ["LOCK", "LOCKED", "CLOSE", "CLOSED"];

function makeTimestampFolderName(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
}

function ensureCaptureFolder({ localRoot } = {}) {
  if (!localRoot) throw new Error("localRoot is required");
  const folderName = makeTimestampFolderName();
  // const folderPath = path.join(localRoot, folderName);
  const folderPath = path.join(process.cwd(), `${folderName}`)
  fs.mkdirSync(folderPath, { recursive: true });
  return { folderName, folderPath };
}

async function requestTopCameraCapture({ action }) {
  try {
    let url;
    if (action === 'ON') {
      url = `${config.cameraApi}/api/zone/0/activate`; 
      // 상단카메라 키는 함수여서 카메라 인덱스 0으로 고정
    } else if (action === 'OFF') {
      url = `${config.cameraApi}/api/zone/${zoneId}/deactivate`;
    } else {
      throw new Error("Invalid action. Use 'ON' or 'OFF'.");
    }

    // 2. 스냅샷 경로와 같이 요청 전송
    const response = await axios.post(url);

    if (response.status === 200) {
      console.log(`Camera Zone 0 ${action} Success:`, response.data);
      return true;
    }

  } catch (error) {
    if (error.response) {
      console.error(`API Error (${action}):`, error.response.data);
    } else {
      console.error(`Request Error (${action}):`, error.message);
    }
    return false;
  }
}

async function requestTopCameraON({ include_top, record_video, folderPath }) {
  try {
    const CameraSaveDirApi =  `${config.cameraApi}/api/recording/start`;
    const response = await axios.post(CameraSaveDirApi, null, {
      params: {
        zone_id: null,
        include_top: include_top,
        record_video: record_video,
        base_path: folderPath
      }
    });

    // 성공 시 응답 데이터 반환
    if (response.status === 200) {
        console.log("Recording Started with Path:", response.data);
        return response.data;
    }

  } catch (error) {
    const errorContext = "requestTopCameraON"; 
    if (error.response) {
      console.error(`API Error (${errorContext}):`, error.response.data);
    } else {
      console.error(`Request Error (${errorContext}):`, error.message);
    }
    return false;
  }
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function requestCameraOFF() {
  try {
    const CameraStopApi =  `${config.cameraApi}/api/recording/stop`;
    // 잠시 대기 후 정지 요청을 보냅니다. 카메라 API는 zone_id 파라미터를 요구할 수 있습니다.
    await delay(5000);
    // const response = await axios.post(CameraStopApi, null, {
    //   params: {
    //     zone_id: 0
    //   }
    // });
    const response = await axios.post(CameraStopApi);
    if (response && response.status === 200) {
      // console.log("Recording Stopped. File Saved at:", response.data);
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

let token = null

async function init() {
    try {
        await axios.post(`${config.ioboardApi}/init`);
    } catch (e) {
        console.error("[IO Board] Init failed", e);
    }
    // --- 1. 이벤트 리스너 설정 ---
    const TokenHandler = new EventSource(`${config.cardTerminalApi}/sse`);
    console.log("[Card Terminal] Listening for card tokens...");

    TokenHandler.addEventListener('tx_token_generate', (event) => {
        // e {"status": "Y", "vankey_hash": "0027057596824048aafeea42", "card_info": {"SERIAL_NUMBER": "", "ACQUIRER_ID": "003", "ACQUIRER_NAME": "\ud558\ub098\uce74\ub4dc", "ISSUER_ID": "003", "ISSUER_NAME": "\ud1a0\uc2a4\ubc45\ud06c\uce74\ub4dc", "MERCHANT_ID": "00915100663"}, "response_code": 0, "message": ""}
        console.log('e', event.data)
        if (event.data) {
            try {
                token = event.data.vankey_hash;
                // const CardMethod = token.startsWith("SPAYKEY") ? "S" : "N"
                const CardMethod = 'N'
                // S = 삼성페이, N = 일반카드
                console.log('[CardToken] Token received:', token);
                
                // 토큰을 받으면 프로세스 시작 (비동기 호출)
                startProcess(token, CardMethod); 
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
    TokenHandler.addEventListener('samsung_pay_init', (event) => {
        console.log('samsungpay::::', event.data); // {}
    });

    // rfid:::: {"data": "1763193013"}
    TokenHandler.addEventListener('rfid_init', (event) => {
        console.log('rfid::::', event.data)
    });
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

// --- 2. 프로세스 시작 및 상태 체크 ---
async function startProcess(token, CardMethod) {
    const CameraStatus = '09'
    const CardTerminalStatus = await CardTerminalStatusAPI()
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
    }
}

/**
 * 결제 취소 요청 함수
 * @param {Object} paymentResult - 결제 승인(Approve) 후 받은 응답 데이터
 * @param {string} originalToken - SSE로 받았던 초기 토큰 (vankey_hash)
 * @param {string} amount - 취소할 금액
 * @param {string} CardMethod - 'S'(삼성페이) or 'N'(일반)
 */
async function cancelPayment(paymentResult, originalToken, amount, CardMethod) {
    console.log(`[PAYMENT] Initiating Cancellation... Method: ${CardMethod}`);

    try {
        let cancelPayload = {};
        let cancelEndpoint = "";
        const authDate = paymentResult.authorization_date;
        const authNum = paymentResult.authorization_number;

        if (!authDate || !authNum) {
            throw new Error("Cannot cancel: Missing authorization info from payment result.");
        }

        if (CardMethod === "S") {
            cancelEndpoint = `${config.cardTerminalApi}/payment/samsung-pay/cancel`;
            
            cancelPayload = {
                amount: amount,
                original_authorization_date: authDate,
                original_authorization_number: authNum,
                vankey: paymentResult.vankey
            };

        } else if (CardMethod === "N") {
            cancelEndpoint = `${config.cardTerminalApi}/payment/token/cancel`;

            cancelPayload = {
                amount: amount,
                original_authorization_date: authDate,
                original_authorization_number: authNum,
                vankey_hash: originalToken
            };
        } else {
            throw new Error("Unknown Payment Method");
        }

        console.log(`[PAYMENT] Sending Cancel Request to ${cancelEndpoint}`, cancelPayload);

        const response = await axios.post(cancelEndpoint, cancelPayload);

        if (response.data && response.data.status === "ok") { // 또는 성공 코드 확인
            console.log("[PAYMENT] Cancellation Successful:", response.data);
            return true;
        } else {
            console.error("[PAYMENT] Cancellation Failed:", response.data);
            return false;
        }

    } catch (error) {
        console.error("[PAYMENT] Cancel API Error:", error.message);
        if (error.response) {
            console.error("Detail:", error.response.data);
        }
        return false;
    }
}

// --- 3. 결제 및 제어 로직 ---
async function Payments(token, CardMethod) {
    const deviceIdx = config.deviceIdx;
    const divisionIdx = config.divisionIdx;
    
    // [3] 상품정보 조회
    const productData = await ProductList({
        division_idx: divisionIdx,
        device_idx: deviceIdx
    });
    console.log("[ProductList] Data Loading Complete:", productData);

    // [4] 카메라 폴더 생성
    const LOCAL_ROOT = path.resolve(process.cwd()); 
    const { folderName, folderPath } = ensureCaptureFolder({ localRoot: LOCAL_ROOT });

    //여기서부터 내일 테스트
    // [5] 문 열기 (OPEN)
    const openResult = await callApiToControlDeadbolt("OPEN");
    if (openResult !== "OPEN" && openResult !== 'UNLOCK') throw new Error(`Failed to open door. Status: ${openResult}`)
    console.log("로드셀 제어까지 완료")

    // await requestTopCameraCapture({ folderPath: folderPath, action: 'ON' });

    const CameraSaveInfo = await requestTopCameraON({ 
        zone_id: 0, 
        include_top: true, 
        record_video: true,   // [중요] 영상 녹화를 하려면 true여야 합니다 
        folderPath: folderPath
    });

    try {
      const LoadcellStartRes = await axios.post(`${config.ioboardApi}/recording/start`, {}); 
    } catch (error) {
      console.error("녹화 시작 실패:", error);
    }

    // [7] 로드셀 무게 정보 실시간 전달
    
    // [8] 로드셀 무게 변화 감지

    // [9] 데드볼트 상태 (close) (sensor → node) + (상단 카메라 off + folder snapshot) 저장 (node → camera python)
    try {
        // 1. 문이 닫히고 로그 경로가 올 때까지 대기
        const closeEventData = await waitForDeadboltClose();
        try {
          const LoadcellStopRes = await axios.post(`${config.ioboardApi}/recording/stop`, {}); 
        } catch (error) {
          console.error("녹화 종료 실패:", error);
        }

        if (closedStates.includes(closeEventData.state)) {
            await requestCameraOFF();
        }
    } catch (error) {
        console.error("[Process Error] Door/Camera Sequence:", error);
        return; // 에러 시 중단
    }

    let LoadcellData = null
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
    try {
        console.log("[Model] Sending data for inference...");
        
        const inferencePayload = {
            ProductList     : productData,
            ImageFolder     : folderName,
            Loadcell        : LoadcellData,
        };

        // 모델 서버 요청 (POST)
        const modelRes = await axios.post(`${config.modelApi}/api/judge/multi-zone`, inferencePayload);
        const inferenceResult = modelRes.data;
        console.log("[Model] Inference Result:", inferenceResult);

        const finalAmount = String(inferenceResult.totalPrice).padStart(9, '0');
        if (modelRes.data.success === true){
          let paymentResponse = null;
          if (CardMethod === "S") {
            paymentResponse = await axios.post(`${config.cardTerminalApi}/payment/samsung-pay/approve`, {
                    // amount: inferenceResult.totalPrice,
                    amount: finalAmount, 
                    authorization_type: "PURCHASE",
                    display_message: "SamsungPay Payment"
                });
          }
          else if (CardMethod === "N"){
            paymentResponse = await axios.post(`${config.cardTerminalApi}/payment/token/approve`, {
                    // amount: inferenceResult.totalPrice,
                    amount: finalAmount,
                    vankey_hash: token 
                });
          }
          else{
            console.log("Undefined Card Method Detected.")
            return;
          }
        }
        // 결제 결과 처리
        let payTime = null
        if (paymentResponse && paymentResponse.status === 200) {
            // console.log("[PAYMENT] Success:", paymentResponse.data);
            const currentDate = new Date();
            payTime = makeTimestampFolderName(currentDate);
            sendToPNT(
              paymentDate = payTime,
              paymentData = paymentResponse,
              inferenceData = inferenceResult,
              folderPath = folderName,
              token = token
            )

        } else {
            console.error("[PAYMENT] Failed:", paymentResponse);
        }

    } catch (error) {
        console.error("[Model] Inference Request Failed:", error.message);
    }
}

module.exports = { Payments, router, init };