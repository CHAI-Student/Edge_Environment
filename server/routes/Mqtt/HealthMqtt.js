const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");

async function HealthMqtt() {
  // divisionIdx 기준으로 토픽 네이밍 예시
  const deviceIdx = config.deviceIdx
  const divisionIdx = config.divisionIdx

  // publish
  const healthCheck = `chai/device/${deviceIdx}/health` // healthcare

  const client = getClient(); // 연결 시작
  client.on("connect", () => {
    console.log("[MQTT] connected");
    
    // health publish interval (connect 이후 시작)
    setInterval(() => {
      const timestamp = Date.now();

      const header = {
        IF_ID: "IF_02",
        IF_SYSID: uuidv4(),
        IF_HOST: "MQTTX",
        IF_DATE: timestamp,
      };

      const body = {
        device_idx: deviceIdx,
        division_idx: divisionIdx,
        camera_status: "09",
        deadbolt_status: "19",
        loadcell_status: "29",
        card_terminal_status: "39",
        edgepc_status: "49"
      };

      const payload = JSON.stringify({ HEADER: header, DATA: body });
      console.log('Health Check', payload)

      client.publish(healthCheck, payload, { qos: 0, retain: false }, (e) => {
        if (e) console.error("[MQTT] publish error:", e.message);
      });
    }, 60000);
  });
}

module.exports = { HealthMqtt };
