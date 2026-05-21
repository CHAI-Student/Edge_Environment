const axios = require("axios");
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");
const { devAutoLogin } = require("../auth");

function formatIfDate(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}`
         + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

const external = axios.create({
  baseURL: config.restApi, // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

// ✅ 외부 API 호출 함수
async function DeviceInfo({
  division_idx = config.divisionIdx,
  device_idx = config.deviceIdx,
} = {}) {
  const token = process.env.JWT_TOKEN;
  if (!token) {
    throw new Error("JWT_TOKEN not set");
  }

  const payload = {
    HEADER: {
      IF_ID: "IF_13",
      IF_SYSID: uuidv4(),
      IF_HOST: "CRKPNTCHAI",
      IF_DATE: formatIfDate(),
    },
    DATA: {
      division_idx,
      device_idx
    },
  };

  const r = await external.post("/chai/device/info", payload, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  return r.data;
}

module.exports = { DeviceInfo };

// event 없이 'node ./server/routes/RestAPI/RestAPIClient.js'로 실행
if (require.main === module) {
  (async () => {
    try {
      console.log("[RestAPIClient] standalone start");

      // 1️⃣ 로그인 → 토큰 발급
      const token = await devAutoLogin();
      if (!token) {
        throw new Error("devAutoLogin failed");
      }

      // 2️⃣ env에 토큰 세팅
      process.env.JWT_TOKEN = token;
      process.env.JWT_TOKEN_AT = Date.now().toString();
      console.log("[RestAPIClient] JWT_TOKEN set..",token);

      // 3️⃣ REST API 호출
      const data = await DeviceInfo({
        division_idx: config.divisionIdx,
        device_idx: config.deviceIdx
      });

      console.log("[RestAPIClient] response:");
      console.dir(data, { depth: null });
    } catch (err) {
      console.error("[RestAPIClient] error:");
      console.error(err.message);
      if (err.response) {
        console.error(err.response.data);
      }
    }
  })();
}
