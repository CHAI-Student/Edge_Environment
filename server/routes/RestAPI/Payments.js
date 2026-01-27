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
  const folderPath = path.join(localRoot, folderName);
  fs.mkdirSync(folderPath, { recursive: true });
  return { folderName, folderPath };
}

async function requestTopCameraCapture({ folderPath, action }) {
  try {
    const response = await axios.post(`${config.cameraApi}/top/${action}`, { save_path: folderPath });
    return response.data;
  } catch (error) {
    console.error("Top Camera Error:", error.message);
    return null;
  }
}

let token = ''

async function init() {
    // --- 1. 이벤트 리스너 설정 ---
    const TokenHandler = new EventSource(`${config.cardTerminalApi}/sse`);
    console.log("[Card Terminal] Listening for card tokens...");

    TokenHandler.addEventListener('tx_token_generate', (event) => {
        // e {"status": "Y", "vankey_hash": "0027057596824048aafeea42", "card_info": {"SERIAL_NUMBER": "", "ACQUIRER_ID": "003", "ACQUIRER_NAME": "\ud558\ub098\uce74\ub4dc", "ISSUER_ID": "003", "ISSUER_NAME": "\ud1a0\uc2a4\ubc45\ud06c\uce74\ub4dc", "MERCHANT_ID": "00915100663"}, "response_code": 0, "message": ""}
        console.log('e', event.data)
        if (event.data) {
            try {
                token = event.data.vankey_hash;
                // const card_method = token.startsWith("SPAYKEY") ? "S" : "N"
                const card_method = 'N'
                // S = 삼성페이, N = 일반카드
                console.log('[CardToken] Token received:', token);
                
                // 토큰을 받으면 프로세스 시작 (비동기 호출)
                startProcess(token, card_method); 
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
// const DeadboltHandler = axios.post(`${config.ioboardApi}/deadbolt`); // 엔드포인트 확인 필요
// function waitForDeadboltClose() {
//     return new Promise((resolve) => {
//         console.log("[Door] Waiting for CLOSE event & Log Path from sensor...");

//         const statusHandler = (event) => {
//             if (!event.data) return;
//             try {
//                 const data = JSON.parse(event.data);
//                 const currentState = data.state || data; 
//                 const logPath = data.log_path || data.logPath || null; // 로그 경로 추출

//                 if (currentState === "CLOSE") {
//                     console.log(`[Door] Event Received: CLOSE. (LogPath: ${logPath})`);
                    
//                     DeadboltHandler.removeEventListener('status', statusHandler);
                    
//                     // 상태뿐만 아니라 로그 경로도 함께 반환
//                     resolve({ 
//                         state: "CLOSE", 
//                         logPath: logPath 
//                     });
//                 }
//             } catch (err) {
//                 console.error("[Door] Event parsing error:", err);
//             }
//         };
//         DeadboltHandler.addEventListener('status', statusHandler);
//     });
// }

// --- 2. 프로세스 시작 및 상태 체크 ---
async function startProcess(token, card_method) {
    // const LoadcellStatus = LoadcellStatusAPI
    const CameraStatus = '09'
    const CardTerminalStatus = await CardTerminalStatusAPI()
    // const DeadboltStatus = DeadboltStatusAPI
    const DeadboltStatus = '19'
    const LoadcellStatus = '29'

    if (CardTerminalStatus == '39' && DeadboltStatus == '19' && LoadcellStatus == '29' && CameraStatus == '09') {
        console.log('[PAYMENT] Health check passed. Starting Payments process...');
        try {
            await Payments(token, card_method);
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
 * @param {string} card_method - 'S'(삼성페이) or 'N'(일반)
 */
async function cancelPayment(paymentResult, originalToken, amount, card_method) {
    console.log(`[PAYMENT] Initiating Cancellation... Method: ${card_method}`);

    try {
        let cancelPayload = {};
        let cancelEndpoint = "";
        const authDate = paymentResult.authorization_date;
        const authNum = paymentResult.authorization_number;

        if (!authDate || !authNum) {
            throw new Error("Cannot cancel: Missing authorization info from payment result.");
        }

        if (card_method === "S") {
            cancelEndpoint = `${config.cardTerminalApi}/payment/samsung-pay/cancel`;
            
            cancelPayload = {
                amount: amount,
                original_authorization_date: authDate,
                original_authorization_number: authNum,
                vankey: paymentResult.vankey
            };

        } else if (card_method === "N") {
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
async function Payments(token, card_method) {
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
    
    await requestTopCameraCapture({ folderPath: folderPath, action: 'on' });

    //여기서부터 내일 테스트
    // [5] 문 열기 (OPEN)
    const openResult = await callApiToControlDeadbolt("OPEN");
    if (openResult !== "OPEN") throw new Error(`Failed to open door. Status: ${openResult}`);

    // [7] 로드셀 무게 정보 실시간 전달
    
    // [8] 로드셀 무게 변화 감지

    // [9] 데드볼트 상태 (close) (sensor → node) + (상단 카메라 off + folder snapshot) 저장 (node → camera python)
    let receivedLogPath = null;
    try {
        // 1. 문이 닫히고 로그 경로가 올 때까지 대기
        const closeEventData = await waitForDeadboltClose(); 
        if (closeEventData.state === "CLOSE") {
            receivedLogPath = closeEventData.logPath; // 경로 저장
            await requestTopCameraCapture({ folderPath: folderPath, action: 'off' });
        }
    } catch (error) {
        console.error("[Process Error] Door/Camera Sequence:", error);
        return; // 에러 시 중단
    }

    try {
        console.log("[Model] Sending data for inference...");
        
        const inferencePayload = {
            product_info: productData,
            image_path: folderPath,
            log_path: receivedLogPath,
        };

        // 모델 서버 요청 (POST) , endpoint 확인 필요
        const modelRes = await axios.post(`${config.modelApi}/inference`, inferencePayload);
        const inferenceResult = modelRes.data;
        console.log("[Model] Inference Result:", inferenceResult);


        const is_inference_success = modelRes.data.success

        if (is_inference_success === 'success'){
          const paymentPayload = {
            amount: inferenceResult.totalPrice,
            vankey_hash: token
          }
          let paymentResponse = null;
          if (card_method === "S") {
            paymentResponse = await axios.post(`${config.cardTerminalApi}/payment/samsung-pay/approve`, {
                    amount: finalAmount, 
                    authorization_type: "PURCHASE",
                    display_message: "SamsungPay Payment"
                });
          }
          else if (card_method === "N"){
            paymentResponse = await axios.post(`${config.cardTerminalApi}/payment/token/approve`, {
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
        if (paymentResponse && paymentResponse.status === 200) {
            console.log("[PAYMENT] Success:", paymentResponse.data);
        } else {
            console.error("[PAYMENT] Failed:", paymentResponse);
        }

    } catch (error) {
        console.error("[Model] Inference Request Failed:", error.message);
    }
}

module.exports = { Payments, router, init };