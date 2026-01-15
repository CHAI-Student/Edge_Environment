// 파이썬에서 import하는 부분
const express = require("express");
const axios = require("axios");
const config = require("../config/key");

const router = express.Router();

const external = axios.create({
  baseURL: config.restApi,
  timeout: 10000,
  headers: { "Content-Type": "application/json" }, // 토큰 인증 시 사용
  withCredentials: false,
});

// dev에서 자동으로 받아둘 토큰(메모리 저장)
let cachedToken = ''; // 개발용 토큰
let cachedRaw = ''; // 응답 원본

async function devAutoLogin() {
  if (process.env.NODE_ENV === "production") return null;

  const userId = config.userId
  const userPassword = config.userPassword
  if (!userId || !userPassword) return null;

  const r = await external.post("/auth/login", {
    loginType: "admin",
    userId: userId,
    userPassword: userPassword,
    ipaddress: "",
  });

  const token = r.data.accessToken

  if (!token) return null;
  else {
    cachedToken = token;
    cachedRaw = r.data;
    // console.log('Token', cachedToken);
    process.env.JWT_TOKEN = cachedToken;
    process.env.JWT_TOKEN_AT = Date.now().toString(); // (선택) 발급시각
    console.log('jwtToken', process.env.JWT_TOKEN);
    return cachedToken; // 토큰 반환
  }
}

module.exports = { router, devAutoLogin };
