require("dotenv").config();
const axios = require("axios");
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");
const { devAutoLogin } = require("../auth");
const { HealthMqtt } = require("../Mqtt/HealthMqtt");
const { ProductList } = require("./ProductList");
const fs = require("fs");
const path = require("path");

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
  console.log('localRoot', localRoot)

  const folderName = makeTimestampFolderName();
  const folderPath = path.join(localRoot, folderName);

  fs.mkdirSync(folderPath, { recursive: true });

  return { folderName, folderPath };
}

async function requestTopCameraCapture({cameraUrl, folderPath,
}) {
  if (!cameraUrl) throw new Error("cameraServerBaseUrl is required");
  if (!folderPath) throw new Error("folderPath is required");

  const controller = new AbortController();
}


async function Payments() {
    const deviceIdx = config.deviceIdx;
    const divisionIdx = config.divisionIdx;
    const jwtToken = config.jwtToken;

    // 토큰 생성 확인 전달 (sensor → node)

    // 냉장고 상태 체크 + 상품정보(IF11) 뷸러오기
    // const deviceHealthCheck = await HealthMqtt(body);
    // console.log('deviceHealthCheck', deviceHealthCheck)
    const productData = await ProductList({
        division_idx: divisionIdx,
        device_idx: deviceIdx
    })
    console.log("[ProductList] response:");
    console.dir(productData, { depth: null });

    // 상단 카메라 request (node → sensor) + 폴더경로 지정
    const LOCAL_ROOT = path.resolve(process.cwd()); 
    // 1) 폴더 생성
    const { folderName, folderPath } = ensureCaptureFolder({ localRoot: LOCAL_ROOT });
    console.log("[CaptureFolder]", { folderName, folderPath });
    // 카메라 실행
    // 2) 상단 카메라 서버로 저장 경로 전달 + 촬영 요청
    const cameraUrl = config.cameraUrl

    const camRes = await requestTopCameraCapture({
        cameraUrl,
        folderPath,
    });

    console.log("[TopCamera] response:");
    console.dir(camRes, { depth: null });

    // 데드볼트 request (node → sensor)
    const apiResultState = await callApiToControlDoor(targetState);
    if (apiResultState === "OPEN" || apiResultState === "CLOSE") {
        finalState = apiResultState;
        resultMsg = finalState === "OPEN" ? "Door is opened" : "Door is closed";
    } else {
        throw new Error(`Unexpected API response: ${apiResultState}`);
    }
    // 상품 정보(상품명, 무게, 재고) + 스냅샷 경로 (node → model)

    // 로드셀 무게 변화 감지 시
    // → 폴더 생성 + 측면 카메라 on (sensor python → node → camera python)	
    // loadcell event Y → N으로 바뀌면 cam python server req X → 10초 뒤에 카메라 off

    // 데드볼트 상태 (close) (sensor → node)

    // 추론 후 결제 정보(총 가격, 상품명, 개수) 전달 (model → node) → 판단시 완전/불완전 상태 파악 필요

    // 단말기로 가격 + 토큰 전달(node → sensor)
 
    // 결제 승인 결과 확인(sensor → node)

    // 결제 정보 → PNT
    
} 

module.exports = { Payments };