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

// 결제 취소 요청이 들어오면 -> 현재 결제 진행 중인지 확인 후 -> 진행 중이면 '아직 처리할 수 없다는 내용 response' : 진행 중이 아니면 CancelPayment 처리
// 결제 취소 -> 삼성 페이, 신용 카드
// token_id	를 활용해 삼성 페이(SPAYKEY~~~)인지 신용카드인지(VANKEY~~~) 판단해 로직 진행

async function CancelPayment() {

    const deviceIdx = config.deviceIdx;
    const cancelPaymentSub = `chai/device/${deviceIdx}/cmd/payment`;
    const cancelPaymentPub = `chai/device/${deviceIdx}/ack/payment`;

    const client = getClient();

    client.on("connect", () => {
        console.log("[CANCEL] MQTT Connected");
        client.subscribe(cancelPaymentSub, { qos: 1 }, (err, granted) => {
            if (err) console.error("[CANCEL] subscribe error:", err.message);
            else console.log("[CANCEL] subscribed:", granted);
        });
    });

    client.on("message", async (topic, payloadBuf) => {
        if (topic !== cancelPaymentSub) return;
        let msg;
        try {
            msg = JSON.parse(payloadBuf.toString());
        } catch (e) {
            console.error("[DEADBOLT] invalid JSON:", payloadBuf.toString());
            return;
        }
    })

    try {
        let cancelPayload = {};
        let cancelEndpoint = "";
        const authDate = paymentResult.authorization_date;
        const authNum = paymentResult.authorization_number;

        if (!authDate || !authNum) {
            throw new Error("Cannot cancel: Missing authorization info from payment result.");
        }

        if (CardMethod === "S") {
            cancelEndpoint = `${config.cardTerminalApi}/payment/samsung-pay/cancel`;
            
            cancelPayload = {
                amount: amount,
                original_authorization_date: authDate,
                original_authorization_number: authNum,
                vankey: paymentResult.vankey
            };

        } else if (CardMethod === "N") {
            cancelEndpoint = `${config.cardTerminalApi}/payment/token/cancel`;

            cancelPayload = {
                amount: amount,
                original_authorization_date: authDate,
                original_authorization_number: authNum,
                vankey_hash: originalToken
            };
        } else {
            throw new Error("Unknown Payment Method");
        }

        console.log(`[PAYMENT] Sending Cancel Request to ${cancelEndpoint}`, cancelPayload);

        const response = await axios.post(cancelEndpoint, cancelPayload);

        if (response.data && response.data.status === "ok") { // 또는 성공 코드 확인
            console.log("[PAYMENT] Cancellation Successful:", response.data);
            return true;
        } else {
            console.error("[PAYMENT] Cancellation Failed:", response.data);
            return false;
        }

    } catch (error) {
        console.error("[PAYMENT] Cancel API Error:", error.message);
        if (error.response) {
            console.error("Detail:", error.response.data);
        }
        return false;
    }
}



module.exports = { CancelPayment };