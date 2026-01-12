const express = require("express");
const axios = require("axios");
const config = require("../config/key");

const router = express.Router();

const external = axios.create({
  baseURL: config.externalApi,
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
  withCredentials: false,
});

// ✅ dev에서 자동으로 받아둘 토큰(메모리 저장)
let cachedToken = null;
let cachedRaw = null;

async function devAutoLogin() {
  if (process.env.NODE_ENV === "production") return null;

  const userId = 'admin';
  const userPassword = 'carrier041!';
  if (!userId || !userPassword) return null;

  const r = await external.post("/auth/login", {
    loginType: "admin",
    userId: userId,
    userPassword: userPassword,
    ipaddress: "",
  });


  // ✅ 여기 토큰 필드는 “외부 응답 스펙”에 맞춰 1개로 확정해야 함
  const token =
    r?.data?.token ??
    r?.data?.data?.token ??
    r?.data?.accessToken ??
    r?.data?.data?.accessToken;

  if (!token) return null;

  cachedToken = token;
  cachedRaw = r.data;
  console.log(JSON.stringify(r.data, null, 2));
  return token; // ✅ 토큰 반환
}

// (1) 일반 로그인: 요청 body로 받아서 외부 호출 → 토큰 반환
router.post("/login", async (req, res) => {
  try {
    const { userId, userPassword, ipaddress = "" } = req.body || {};
    if (!userId || !userPassword) {
      return res.status(400).json({ ok: false, error: "userId and userPassword are required" });
    }

    const payload = { loginType: "admin", userId, userPassword, ipaddress };
    const r = await external.post("/auth/login", payload);

    const token =
      r?.data?.token ??
      r?.data?.data?.token ??
      r?.data?.accessToken ??
      r?.data?.data?.accessToken;

    if (!token) {
      return res.status(502).json({ ok: false, error: "token not found", external: r.data });
    }

    return res.json({ ok: true, token, external: r.data });
  } catch (err) {
    return res.status(err?.response?.status || 502).json({
      ok: false,
      error: err?.response?.data || err?.message || "External login failed",
    });
  }
});

// (2) dev에서 자동으로 받은 토큰 확인용(선택)
router.get("/token", (req, res) => {
  return res.json({ ok: true, token: cachedToken, external: cachedRaw });
});

module.exports = { router, devAutoLogin };
