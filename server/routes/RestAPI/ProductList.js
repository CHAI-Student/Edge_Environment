const axios = require("axios");
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");
const { devAutoLogin } = require("../auth");

const external = axios.create({
  baseURL: config.restApi, // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

// 외부 API 호출 함수
async function ProductList({
  division_idx = config.divisionIdx,
  device_idx = null,
  product_idx = null,
} = {}) {
  const token = process.env.JWT_TOKEN;
  if (!token) {
    throw new Error("JWT_TOKEN not set");
  }

  const payload = {
    HEADER: {
      IF_ID: "IF_11",
      IF_SYSID: uuidv4(),
      IF_HOST: "CHAI",
      IF_DATE: Date.now(),
    },
    DATA: {
      division_idx,
      device_idx,
      product_idx,
    },
  };

  const r = await external.post("/chai/product/list", payload, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  return r.data;
}

module.exports = { ProductList };

// event 없이 'node ./server/routes/RestAPI/RestAPIClient.js'로 실행
if (require.main === module) {
  (async () => {
    try {
      console.log("[RestAPIClient] standalone start");

      // 로그인 → 토큰 발급
      const token = await devAutoLogin();
      if (!token) {
        throw new Error("devAutoLogin failed");
      }

      // env에 토큰 세팅
      process.env.JWT_TOKEN = token;
      process.env.JWT_TOKEN_AT = Date.now().toString();
      console.log("[RestAPIClient] JWT_TOKEN set");

      // REST API 호출
      const data = await ProductList({
        division_idx: config.divisionIdx,
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
