// ============================================================
// payment.js — 수동 실행용 테스트 스크립트 (node server/test/payment.js)
// 역할: 카드 단말기 응답 mock(status "Y") -> health check mock(card terminal/
//       deadbolt/loadcell/camera) -> ProductList 호출 -> camera snapshot 폴더
//       생성까지 payment 시작 흐름을 mock 기반으로 검증한다.
// ============================================================
const fs = require("fs");
const path = require("path");

// 네 프로젝트 구조에 맞게 경로 조정
const config = require("../config/key");
const { ProductList } = require("../routes/RestAPI/ProductList"); // ← 실제 파일 위치로 수정
const { devAutoLogin } = require("../routes/auth"); // ← 실제 파일 위치로 수정
// const { Payments } = require("../routes/HTTP/Payments"); // ← 실제 파일 위치로 수정

// 0) Health 체크용 Mock 함수들
function healthCheck() {
  // TODO: 나중에 실제 API 결과로 교체
  const CardTerminalStatus = "39";
  const DeadboltStatus = "19";
  const LoadcellStatus = "29";
  const CameraStatus = "09";

  const ok =
    CardTerminalStatus === "39" &&
    DeadboltStatus === "19" &&
    LoadcellStatus === "29" &&
    CameraStatus === "09";

  return {
    ok,
    detail: {
      CardTerminalStatus,
      DeadboltStatus,
      LoadcellStatus,
      CameraStatus,
    },
  };
}



// ---------- 1) 카드 단말기 응답 Mock ----------
function mockCardTerminalResponse() {
  return {
    status: "Y", // ✅ 성공 가정
    vankey_hash: "123456789012345678901234", // 길이 24
    card_info: {
      // 필요한 값만 넣어도 됨
      card_no_masked: "1234-****-****-5678",
      issuer: "TEST_BANK",
      // amount, 승인번호 등 추가 가능
    },
    response_code: 0,
    message: "APPROVED",
  };
}

// ---------- 2) 폴더명/폴더 생성 ----------
function makeFolderName(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
}

function makeCameraFolder({ localRoot } = {}) {
  if (!localRoot) throw new Error("localRoot is required");

  const folderName = makeFolderName();
  const folderPath = path.join(localRoot, folderName);

  fs.mkdirSync(folderPath, { recursive: true });

  return { folderName, folderPath };
}

// ---------- 3) 테스트 실행 ----------
async function testFlow() {
  console.log("=== TEST START ===");

  // (A) 카드 단말기에서 status:'Y' 수신 가정
  const terminalRes = mockCardTerminalResponse();
  console.log("[CardTerminal] mock response:", terminalRes);

  if (terminalRes.status !== "Y") {
    console.log("[PAYMENT] status is not Y -> stop");
    return;
  }

  // (B) JWT_TOKEN 확인 (ProductList가 Bearer로 쓰는 토큰)
//   로그인 → 토큰 발급 (나중에 삭제 필요 -> 결제 시엔 이미 발급된 config 토큰 활용)
  const token = await devAutoLogin();
  if (!token) {
    throw new Error("devAutoLogin failed");
  }
//   const token = config.jwtToken;

  if (!token) {
    throw new Error("JWT_TOKEN not set. Example: JWT_TOKEN=xxxxx node test_payment_flow.js");
  }
  console.log("[Auth] JWT_TOKEN prefix:", token.slice(0, 20), "...");

  // 장비 상태 확인
  (async () => {
    const health = healthCheck();

    if (!health.ok) {
        console.log("[PAYMENT] health status is bad, it cannot run", health.detail);
        return;
    }

    console.log("[PAYMENT] health check passed, starting Payments process");
    // 이 부분은 이제 X
    // await Payments();
    })().catch((e) => {
    console.error("[PAYMENT] fatal error:", e?.response?.data || e.message || e);
    });

  // (C) 상품 정보(IF11) 호출
  const divisionIdx = config.divisionIdx;
  const deviceIdx = config.deviceIdx;

  console.log("[ProductList] calling with:", { divisionIdx, deviceIdx });

  const productData = await ProductList({
    division_idx: divisionIdx,
    device_idx: deviceIdx,
  });

  console.log("[ProductList] response (top-level):");
  console.dir(productData, { depth: null });

  // (D) 폴더 경로 생성 (LOCAL_ROOT 아래에 날짜_시간 폴더)
  const LOCAL_ROOT = path.resolve(process.cwd()); // 예: /Users/yoona/Downloads/Edge_Environment
  const { folderName, folderPath } = makeCameraFolder({ localRoot: LOCAL_ROOT });

  console.log("[CameraFolder] created:", { folderName, folderPath });

  console.log("=== TEST DONE ===");
  return { terminalRes, productData, folderName, folderPath };
}

// 실행
testFlow().catch((e) => {
  console.error("[TEST] failed:", e?.response?.data || e.message || e);
});
