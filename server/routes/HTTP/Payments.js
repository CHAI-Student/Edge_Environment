require("dotenv").config();
const axios = require("axios");
const config = require("../../config/key");
const { callApiToControlDoor } = require('../Mqtt/DoorApiService')
const { ProductList } = require("../RestAPI/ProductList");
const fs = require("fs");
const path = require("path");
const EventSource = require('eventsource');

function FolderName(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
}

function MakeCameraFolder({ localRoot } = {}) {
  if (!localRoot) throw new Error("localRoot is required");
  console.log('localRoot', localRoot)

  const folderName = FolderName();
  const folderPath = path.join(localRoot, folderName);

  fs.mkdirSync(folderPath, { recursive: true });

  return { folderName, folderPath };
}
// 1. 카드 단말기에서 토큰 생성 확인
const cardTerminalApi = config.cardTerminalApi;
const TokenHandler = new EventSource(`${cardTerminalApi}/token`);

const token = '';

TokenHandler.addEventListener('token', (event) => {
    if (event.data) {
        const token = JSON.parse(event.data);
        console.log('[CardToken] Token received:', token);
    } else {
        console.log('[CardToken] No token data received');
    }
    return token;
})

// 2. 장비 상태 체크
// const apiCardTerminalStatus = callCardTerminalStatusApi();
// const apiDeadboltStatus = callIOStatusApi();
const CardTerminalStatus = "39" // 현재는 값을 못불러오니, 이렇게 지정
const DeadboltStatus = "19" // 현재는 값을 못불러오니, 이렇게 지정
const LoadcellStatus = "29" // 현재는 값을 못불러오니, 이렇게 지정
const CameraStatus = "09" // 현재는 값을 못불러오니, 이렇게 지정

if (CardTerminalStatus == '39' && DeadboltStatus == '19' && LoadcellStatus == '29' && CameraStatus == '09') {
    console.log('[PAYMENT] health check passed, starting Payments process')
    Payments();
} else {
    console.log('[PAYMENT] health status is bad, it cannot run')
}
    

async function Payments() {
    const deviceIdx = config.deviceIdx;
    const divisionIdx = config.divisionIdx;
    const jwtToken = config.jwtToken;

    // 상품정보(IF11) 뷸러오기
    const productData = await ProductList({
        division_idx: divisionIdx,
        device_idx: deviceIdx
    })
    console.log("[ProductList] response:");
    console.dir(productData, { depth: null });

    // 상단 카메라 request (node → sensor) + 폴더경로 지정
    const LOCAL_ROOT = path.resolve(process.cwd()); 
    // 1) 폴더 생성
    const { folderName, folderPath } = MakeCameraFolder({ localRoot: LOCAL_ROOT });
    console.log("[CameraFolder]", { folderName, folderPath });
    // 카메라 실행
    // 2) 상단 카메라 서버로 저장 경로 전달 + 촬영 요청
    const cameraUrl = config.cameraApi
    const camRes = await axios.post(`${cameraUrl}`)
    console.log("[Camera] response:", camRes.data);

    // 데드볼트 request (node → sensor)
    const apiResultState = await callApiToControlDoor(targetState);
    if (apiResultState === "OPEN" || apiResultState === "CLOSE") {
        finalState = apiResultState;
        resultMsg = finalState === "CLOSE" ? "OPEN" : "Door is closed";
    } else {
        throw new Error(`Unexpected API response: ${apiResultState}`);
    }
    // 상품 정보(상품명, 무게, 재고) + 스냅샷 경로 (node → model)



    // 데드볼트 상태 (close) (sensor → node)



    // 추론 후 결제 정보(총 가격, 상품명, 개수) 전달 (model → node) → 판단시 완전/불완전 상태 파악 필요



    // 단말기로 가격 + 토큰 전달(node → sensor)
 


    // 결제 승인 결과 확인(sensor → node)



    // 결제 정보 → PNT
    
} 

module.exports = { Payments };