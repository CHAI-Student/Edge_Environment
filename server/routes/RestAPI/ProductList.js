require("dotenv").config();
const axios = require("axios");
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");
const express = require("express");
const router = express.Router();

const external = axios.create({
  baseURL: config.restApi, // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

// 외부 API 호출 함수
async function ProductList({
  division_idx = config.divisionIdx,
  device_idx = null
} = {}) {
  const token = config.jwtToken
  console.log("[PRODUCT] JWT_TOKEN =", token);
  if (!token) {
    console.log("[DEBUG] config resolved =", require.resolve("../../config/key"));
    console.log("[DEBUG] jwtToken =", config.jwtToken);
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
      division_idx: division_idx,
      device_idx: device_idx,
    },
  };

  const r = await external.post("/chai/product/list", payload, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  return r.data;
}

module.exports = { ProductList, router };