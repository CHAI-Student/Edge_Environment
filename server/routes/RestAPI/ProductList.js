require("dotenv").config();
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
  const token = config.jwtToken
  console.log("[test] JWT_TOKEN =", process.env.JWT_TOKEN);
  console.log(token)
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

// // event 없이 'node ./server/routes/RestAPI/ProductList.js'로 실행
if (require.main === module) {
  (async () => {
    try {
      console.log("[ProductList] standalone start");

      // 로그인 → 토큰 발급 (나중에 삭제 필요 -> 결제 시엔 이미 발급된 config 토큰 활용)
      const token = await devAutoLogin();
      if (!token) {
        throw new Error("devAutoLogin failed");
      }
      // const token = process.env.JWT_TOKEN;

      // env에 토큰 세팅 (나중에 삭제 필요 -> 결제 시엔 이미 발급된 config 토큰 활용)
      process.env.JWT_TOKEN = token;
      process.env.JWT_TOKEN_AT = Date.now().toString();
      console.log("[ProductList] JWT_TOKEN set");

      // REST API 호출
      const data = await ProductList({
        division_idx: config.divisionIdx,
        device_idx: config.deviceIdx
      });

      console.log("[ProductList] response:");
      console.dir(data, { depth: null });
    } catch (err) {
      console.error("[ProductList] error:");
      console.error(err.message);
      if (err.response) {
        console.error(err.response.data);
      }
    }
  })();
}
