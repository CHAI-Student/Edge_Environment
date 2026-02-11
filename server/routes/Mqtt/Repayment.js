// 결제 취소 요청이 들어오면 -> 현재 결제 진행 중인지 확인 후 -> 진행 중이면 '아직 처리할 수 없다는 내용 response' : 진행 중이 아니면 CancelPayment 처리
// 결제 취소 -> 삼성 페이, 신용 카드
// token_id 를 활용해 삼성 페이(SPAYKEY~~~)인지 신용카드인지(VANKEY~~~) 판단해 로직 진행

// 재결제 기능 진행 --> 신용카드 (삼성 페이 X)
// 재결제 기능이 들어오면 -> 새로운 금액으로 결제를 진행하고 -> 이전 결제는 vankey로 다시 취소 처리 필요

const axios = require("axios");
const config = require("../../config/key");
const { getClient } = require("./MqttClient");
const { getProcessing } = require("../RestAPI/PaymentProcessing");
const { v4: uuidv4 } = require("uuid");

// 토큰 prefix로 결제 타입 판단
function getCardMethod(tokenId = "") {
  if (tokenId.startsWith("SPAYKEY")) return "S"; // Samsung Pay
  if (tokenId.startsWith("VANKEY")) return "N";  // Credit Card
}

// 서버 시작 시 1회만 호출해서 구독/처리 루프를 올리는 방식 추천
function Repayment() {
  const deviceIdx = config.deviceIdx;
  const repaymentSub = `chai/device/${deviceIdx}/cmd/payment`;
  const repaymentPub = `chai/device/${deviceIdx}/ack/payment`;

  const client = getClient();

  const Subscribe = () => {
    client.subscribe(repaymentSub, { qos: 1 }, (err) => {
      if (err) console.error("[REPAY] subscribe error:", err.message);
      else console.log("[REPAY] subscribed:", repaymentSub);
    });
  };

  if (client.connected) Subscribe();
  client.on("connect", () => {
    console.log("[REPAY] MQTT Connected");
    Subscribe();
  });

  client.on("message", async (topic, payloadBuf) => {
    if (topic !== repaymentSub) return;

    let res;
    try {
      res = JSON.parse(payloadBuf.toString());
    } catch (e) {
      console.error("[REPAY] invalid JSON:", payloadBuf.toString());
      return;
    }

    if (res.request_type == "CANCEL") {
      console.log("[CANCEL] response data:", res);

      // 진행 중이면 취소 불가 ACK
      if (getProcessing()) {
        const ifSysId = res.HEADER.IF_SYSID || uuidv4();
        const timestamp = Date.now();

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CHAI",
            IF_DATE: timestamp,
          },
          DATA: {
            // 4번(추적 필드) 포함
            device_idx: res.device_idx,
            division_idx: res.division_idx,
            payment_idx: res.payment_idx,
            token_id: res.token_id,
            request_type: "CANCEL",
            result_cd: "F",
            result_msg: "현재 카드단말기가 이용중입니다. 잠시 후 다시 시도해주세요",
          },
        });

        client.publish(repaymentPub, ackPayload, { qos: 1, retain: false }, (e) => {
          if (e) console.error("[CANCEL] Publish Error:", e.message);
          else console.log("[CANCEL] Busy ACK sent");
        });
        return;
      }

      // token_id 로 카드 방식 결정
      const cardMethod = getCardMethod(res.token_id);

      let cancelEndpoint = "";
      let cancelPayload = {};

      if (cardMethod === "S") {
        cancelEndpoint = `${config.cardTerminalApi}/payment/samsung-pay/cancel`;
        cancelPayload = {
          amount: res.approve_price,
          original_authorization_date: res.approve_at,
          original_authorization_number: res.approve_no,
          vankey: res.token_id,
        };
      } else if (cardMethod === "N") {
        cancelEndpoint = `${config.cardTerminalApi}/payment/token/cancel`;
        cancelPayload = {
          amount: res.approve_price,
          original_authorization_date: res.approve_at,
          original_authorization_number: res.approve_no,
          vankey_hash: res.token_id,
        };
      } else {
        console.error("[CANCEL] Unknown Payment Method:", res.token_id);
        return;
      }

      console.log(`[CANCEL] Sending Cancel Request to ${cancelEndpoint}`, cancelPayload);

      const response = await axios.post(cancelEndpoint, cancelPayload);

      if (response.data && response.data.status === "ok") {
        console.log("[CANCEL] Cancellation Successful:", response.data);

        const ifSysId = (res.HEADER && res.HEADER.IF_SYSID) ? res.HEADER.IF_SYSID : uuidv4();
        const timestamp = Date.now();

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CHAI",
            IF_DATE: timestamp,
          },
          DATA: {
            device_idx: response.data.device_idx,
            division_idx: response.data.division_idx,
            payment_idx: response.data.payment_idx,
            token_id: response.data.token_id,
            org_token_id: "null",
            request_type: "CANCEL",
            approve_at: timestamp,
            approve_price: response.data.approve_price,
            approve_no: response.data.approve_no,
            org_approve_at: "null",
            org_approve_price: "null",
            org_approve_no: "null",
            result_cd: "S",
            result_msg: "취소가 완료되었습니다",
          },
        });

        client.publish(repaymentPub, ackPayload, { qos: 1, retain: false }, (e) => {
          if (e) console.error("[CANCEL] Publish Error:", e.message);
          else console.log("[CANCEL] Success ACK sent");
        });
      } else {
        console.error("[CANCEL] Cancellation Failed:", response.data);
      }
    } else if (res.request_type == "REPAY") {
      console.log("[REPAY] response data:", res);
    }
  });
}

module.exports = { Repayment };