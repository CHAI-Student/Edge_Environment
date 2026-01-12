const axios = require("axios");
const config = require("../../config/key");

if (!config.externalApi) {
  throw new Error("Missing EXTERNAL_API");
}

const externalApi = axios.create({
  baseURL: config.externalApi, // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 8000,
  withCredentials: false,
  headers: {
    "Content-Type": "application/json",
  },
});

module.exports = externalApi;

