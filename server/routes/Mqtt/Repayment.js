require("dotenv").config();
const axios = require("axios");
const config = require("../../config/key");
const express = require("express");
const router = express.Router();
const { getClient, subscribe } = require("./MqttClient");
const { CardTerminalStatusAPI, DeadboltStatusAPI, LoadcellStatusAPI, CameraStatusAPI } = require('./HealthMqtt')
const { ProductList } = require("../RestAPI/ProductList");
const fs = require("fs");
const path = require("path");
const { callApiToControlDeadbolt } = require('./DeadboltApiService'); // [추가] 도어 제어 함수 임포트 가정
const { EventSource } = require('eventsource');
const { sendToPNT } = require("../RestAPI/PaymentStore");
const { exec } = require("child_process");
const os = require("os");

// 재결제 기능 진행 --> 신용카드 (삼성 페이 X)
// 재결제 기능이 들어오면 -> 새로운 금액으로 결제를 진행하고 -> 이전 결제는 vankey로 다시 취소 처리 필요

async function Repayment() {
    
}

module.exports = { Repayment }