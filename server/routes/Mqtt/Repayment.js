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

function formatIfDate(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}`
         + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function approveDate(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}`;
        //  + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

// 서버 시작 시 1회만 호출해서 구독/처리 루프를 올리는 방식 추천
function Repayment() {
  const deviceIdx = config.deviceIdx;
  const repaymentSub = `chai/device/${deviceIdx}/cmd/payment`;
  const repaymentPub = `chai/device/${deviceIdx}/ack/payment`;

  const client = getClient();

  client.subscribe(repaymentSub, { qos: 1 }, (err, granted) => {
    if (err) {
      console.error("[DoorCollect] Subscribe Error:", err.message);
      return;
    }

    console.log("[DoorCollect] Subscribe granted:", granted);
    // console.log(`[DoorCollect] Subscribed: ${subTopic}`);
  });

  // const client = getClient();

  // const subscribeRepayment = () => {
  //   console.log("[REPAY] subscribing:", repaymentSub);

  //   client.subscribe(repaymentSub, { qos: 1 }, (err, granted) => {
  //     if (err) {
  //       console.error("[REPAY] Subscribe Error:", err.message);
  //       return;
  //     }

  //     console.log("[REPAY] subscribed:", granted);
  //   });
  // };

  // if (client.connected) {
  //   subscribeRepayment();
  // } else {
  //   console.log("[REPAY] MQTT Connected");
  //   };

  client.on("message", async (topic, payloadBuf) => {
    if (topic !== repaymentSub) return;

    console.log("[REPAY] message received:", topic);
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
        const ifSysId = (res.HEADER && res.HEADER.IF_SYSID) ? res.HEADER.IF_SYSID : uuidv4();

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CRKPNTCHAI",
            IF_DATE: formatIfDate(),
          },
          DATA: {
            device_idx: res.device_idx,
            division_idx: res.division_idx,
            payment_idx: res.payment_idx,
            token_id: res.token_id,
            request_type: "CANCEL",
            result_cd: "F",
            result_msg: "[결제 취소] 현재 카드단말기가 이용중입니다. 잠시 후 다시 시도해주세요",
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

        // ✅ Unknown 케이스도 실패 ACK (선택이지만 운영상 권장)
        const ifSysId = (res.HEADER && res.HEADER.IF_SYSID) ? res.HEADER.IF_SYSID : uuidv4();

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CRKPNTCHAI",
            IF_DATE: formatIfDate(),
          },
          DATA: {
            device_idx: res.device_idx,
            division_idx: res.division_idx,
            payment_idx: res.payment_idx,
            token_id: res.token_id,
            request_type: "CANCEL",
            result_cd: "F",
            result_msg: "[결제 취소] Unknown Payment Method (token_id prefix)",
          },
        });

        client.publish(repaymentPub, ackPayload, { qos: 1, retain: false }, () => {});
        return;
      }

      console.log(`[CANCEL] Sending Cancel Request to ${cancelEndpoint}`, cancelPayload);

      // ✅ 여기부터 “2번 보완”: 실패/예외도 ACK를 보냄
      let response;
      try {
        response = await axios.post(cancelEndpoint, cancelPayload);
      } catch (err) {
        console.error("[CANCEL] Cancel API error:", err.message, err.response?.data);

        const ifSysId = (res.HEADER && res.HEADER.IF_SYSID) ? res.HEADER.IF_SYSID : uuidv4();

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CRKPNTCHAI",
            IF_DATE: formatIfDate(),
          },
          DATA: {
            device_idx: res.device_idx,
            division_idx: res.division_idx,
            payment_idx: res.payment_idx,
            token_id: res.token_id,
            request_type: "CANCEL",
            result_cd: "F",
            result_msg: `[결제 취소] 취소 요청 실패: ${err.message}`,
            // 필요하면 단말 응답도 붙여서 디버깅
            terminal_response: err.response?.data ?? null,
          },
        });

        client.publish(repaymentPub, ackPayload, { qos: 1, retain: false }, (e) => {
          if (e) console.error("[CANCEL] Publish Error:", e.message);
          else console.log("[CANCEL] Fail ACK sent (exception)");
        });
        return;
      }

      const ok = response?.data?.response_code == 0 && response?.data?.status === "Y";

      if (ok) {
        console.log("[CANCEL] Cancellation Successful:", response.data);

        const ifSysId = (res.HEADER && res.HEADER.IF_SYSID) ? res.HEADER.IF_SYSID : uuidv4();

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CRKPNTCHAI",
            IF_DATE: formatIfDate(),
          },
          DATA: {
            device_idx: response.data.device_idx,
            division_idx: response.data.division_idx,
            payment_idx: response.data.payment_idx,
            token_id: response.data.token_id,
            org_token_id: "null",
            request_type: "CANCEL",
            payment_at: formatIfDate(),
            approve_at: approveDate(),
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

        // ✅ 실패 ACK 추가 (2번 보완의 핵심)
        const ifSysId = (res.HEADER && res.HEADER.IF_SYSID) ? res.HEADER.IF_SYSID : uuidv4();

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CRKPNTCHAI",
            IF_DATE: formatIfDate(),
          },
          DATA: {
            device_idx: res.device_idx,
            division_idx: res.division_idx,
            payment_idx: res.payment_idx,
            token_id: res.token_id,
            request_type: "CANCEL",
            result_cd: "F",
            result_msg: "[결제 취소] 취소 실패(단말 응답 오류)",
            terminal_response: response.data ?? null,
          },
        });

        client.publish(repaymentPub, ackPayload, { qos: 1, retain: false }, (e) => {
          if (e) console.error("[CANCEL] Publish Error:", e.message);
          else console.log("[CANCEL] Fail ACK sent (rejected)");
        });
      }
    } else if (res.request_type == "REPAY") {
      // 재결제 기능 진행 --> 신용카드 (삼성 페이 X)
      // 재결제 기능이 들어오면 -> 새로운 금액으로 결제를 진행하고 -> 이전 결제는 vankey로 다시 취소 처리 필요
      console.log("[REPAY] response data:", res);

      let ifSysId = res.HEADER.IF_SYSID || uuidv4();

      // 진행 중이면 취소 불가 ACK
      if (getProcessing()) {

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CRKPNTCHAI",
            IF_DATE: formatIfDate(),
          },
          DATA: {
            device_idx: res.device_idx,
            division_idx: res.division_idx,
            payment_idx: res.payment_idx,
            token_id: res.token_id,
            request_type: "REPAY",
            result_cd: "F",
            result_msg: "[재결제] 현재 카드단말기가 이용중입니다. 잠시 후 다시 시도해주세요",
          },
        });

        client.publish(repaymentPub, ackPayload, { qos: 1, retain: false }, (e) => {
          if (e) console.error("[REPAY] Publish Error:", e.message);
          else console.log("[REPAY] Busy ACK sent");
        });
        return;
      }

      // token_id 로 신용카드가 맞는지 확인
      const cardMethod = getCardMethod(res.token_id);
      //승인 후 취소 방식 채택
      if (cardMethod === "N") {
        //새로운 결제 승인
        const oldToken = res.token_id
        const oldApproveAt = res.approve_at
        const oldApprovePrice = res.approve_price // 여기에 새로 결제할 가격 정보가 들어오는건지 아니면 old_approve_price로 들어오는 건지 확인 필요 (0213)
        const oldApproveNo = res.approve_no

        let paymentAt = null;
        let newApproveNo = null;
        let newApproveAt = null;
        let newApprovePrice = null;
        let newToken = null;
        let approveJson = null;

        axios.post(`${config.cardTerminalApi}/payment/token/approve`, {
          amount: oldApprovePrice,
          vankey_hash: oldToken
        }).then((response) => {
          if (response.data.status == 'Y' && response.data.response_code == 0) {
            console.log('[REPAY] response success: ', response.data)
            paymentAt = formatIfDate();
            newApproveNo = response.data.authorization_number
            newApproveAt = response.data.authorization_date
            newApprovePrice = oldApprovePrice
            newToken = response.data.vankey
            approveJson = response.data
          }
          axios.post(`${config.cardTerminalApi}/payment/token/cancel`, {
            amount: oldApprovePrice,
            original_authorization_date: oldApproveAt,
            original_authorization_number: oldApproveNo,
            vankey_hash: oldToken,
          }).then((canRes) => {
            if (canRes.data.status == 'Y' && canRes.data.response_code == 0) console.log('[REPAY/CANCEL] repayment cancel is successful: ', canRes);
          })
        })
        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CRKPNTCHAI",
            IF_DATE: formatIfDate(),
          },
          //여기 마무리
          DATA: {
            device_idx: res.device_idx,
            division_idx: res.division_idx,
            payment_idx: res.payment_idx,
            token_id: newToken,
            org_token_id: oldToken,
            payment_at: paymentAt,
            request_type: "REPAY",
            approve_at: newApproveAt,
            approve_price: newApprovePrice,
            approve_no: newApproveNo,
            org_approve_at: oldApproveAt,
            org_approve_price: oldApprovePrice,
            org_approve_no: oldApproveNo,
            result_cd: "S",
            result_msg: "재결제가 완료되었습니다",
          },
        });

        client.publish(repaymentPub, ackPayload, { qos: 1, retain: false }, (e) => {
          if (e) console.error("[REPAY] Publish Error:", e.message);
          else console.log("[REPAY] Success ACK sent");
        });
      } else if (cardMethod == 'S') {
        console.log('[REPAY] SamsungPay cannot use Repay system')

        const ifSysId = res.HEADER.IF_SYSID || uuidv4();

        const ackPayload = JSON.stringify({
          HEADER: {
            IF_ID: "IF_09",
            IF_SYSID: ifSysId,
            IF_HOST: "CRKPNTCHAI",
            IF_DATE: formatIfDate(),
          },
          DATA: {
            device_idx: res.device_idx,
            division_idx: res.division_idx,
            payment_idx: res.payment_idx,
            token_id: res.token_id,
            request_type: "REPAY",
            result_cd: "F",
            result_msg: "[재결제] 삼성페이는 재결제가 불가합니다. 결제 취소를 이용해주세요.",
          },
        });

        client.publish(repaymentPub, ackPayload, { qos: 1, retain: false }, (e) => {
          if (e) console.error("[REPAY] Publish Error:", e.message);
          else console.log("[REPAY] Busy ACK sent");
        });
        return;
      } else {
        console.error("[CANCEL] Unknown Payment Method:", res.token_id);
        return;
      }
    }
  });
}

module.exports = { Repayment };