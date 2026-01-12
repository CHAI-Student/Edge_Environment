const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");

async function initMqtt() {
  // divisionIdx 기준으로 토픽 네이밍 예시
  const division = config.divisionIdx || "default";

  // ✅ 예시 토픽 (원하는 규칙에 맞게 바꿔)
  const topics = [
    `edge/${division}/sensor/#`, // 센서 -> 로직
    `edge/${division}/cmd/#`, // 명령/제어
  ];

  getClient(); // 연결 시작
  await subscribe(topics);
}

module.exports = { initMqtt };
