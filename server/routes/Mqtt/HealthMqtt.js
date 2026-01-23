const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const axios = require("axios");

const IO_BOARD_API_URL = config.ioBoardUrl || "http://localhost:8001";

async function callIOStatusApi() {
  try {
    const response = await axios.get(`${IO_BOARD_API_URL}/status`, {
      timeout: 5000
    });

    // door: OPEN/CLOSED, deadbolt: OPEN/LOCKED
    if (response.data.door === 'CLOSED' && response.data.deadbolt === 'LOCKED') {
      return '19'; // 정상 상태
    } else {
      return '20'; // 이상 상태
    }
  } catch (error) {
    console.error('[HealthMqtt] IO Status API error:', error.message);
    return '21'; // API 에러
  }
}

async function HealthMqtt() {
  const deviceIdx = config.deviceIdx;
  const divisionIdx = config.divisionIdx;

  const healthCheck = `chai/device/${deviceIdx}/health`;

  const client = getClient();
  client.on("connect", () => {
    console.log("[MQTT] connected");

    // health publish interval
    setInterval(async () => {
      const timestamp = Date.now();

      // IO Board 상태 조회
      const apiDeadboltStatus = await callIOStatusApi();

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
        deadbolt_status: apiDeadboltStatus,
        loadcell_status: "29",
        card_terminal_status: "39",
        edgepc_status: "49"
      };

      const payload = JSON.stringify({ HEADER: header, DATA: body });
      console.log('[HealthMqtt] Publishing:', payload);

      client.publish(healthCheck, payload, { qos: 0, retain: false }, (e) => {
        if (e) console.error("[MQTT] publish error:", e.message);
      });
    }, 60000);
  });
}

module.exports = { HealthMqtt, callIOStatusApi };
