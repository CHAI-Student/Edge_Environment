// ============================================================
// externalApi.js
// 역할: 클라우드(CHAI) 외부 REST API 호출용 axios 인스턴스(baseURL:
//       config.externalApi, timeout 8초, JSON 헤더)를 만들어 내보내는 middleware.
// 상태: 파일 전체가 주석 처리되어 현재 미사용(비활성) 상태이며,
//       어디에서도 require되지 않는다. 참고: require 경로가 "../../config/key"로
//       되어 있어 주석 해제 시 "../config/key"로 수정이 필요해 보인다.
// ============================================================
// const axios = require("axios");
// const config = require("../../config/key");

// if (!config.externalApi) {
//   throw new Error("Missing EXTERNAL_API");
// }

// const externalApi = axios.create({
//   baseURL: config.externalApi, // https://apichaidev.atcrk.co.kr/api/v1
//   timeout: 8000,
//   withCredentials: false,
//   headers: {
//     "Content-Type": "application/json",
//   },
// });

// module.exports = externalApi;
