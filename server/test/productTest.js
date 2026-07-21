// ============================================================
// productTest.js — 수동 실행용 테스트 스크립트 (node ./server/test/productTest.js)
// 역할: devAutoLogin으로 JWT 토큰을 발급받아 env에 세팅한 뒤
//       ProductList REST API(IF11)를 단독 호출해 상품 목록 응답을 확인한다.
// ============================================================
require("dotenv").config();
const axios = require("axios");
const config = require("../config/key");
const { v4: uuidv4 } = require("uuid");
const express = require("express");
const router = express.Router();
const { devAutoLogin } = require("../routes/auth");
const { ProductList } = require("../routes/RestAPI/ProductList");

const external = axios.create({
  baseURL: "https://apichaidev.atcrk.co.kr/api/v1", // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

// event 없이 'node ./server/test/productTest.js'로 실행

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
        device_idx: null
      });

      console.log("[ProductList] response:");
      // console.dir(data, { depth: null });
      console.log(data.DATA.product_list)
    } catch (err) {
      console.error("[ProductList] error:");
      console.error(err.message);
      if (err.response) {
        console.error(err.response.data);
      }
    }
  })();
}