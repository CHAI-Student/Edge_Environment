const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const axios = require("axios");

const IO_BOARD_API_URL = config.ioBoardUrl || "http://localhost:8001";

async function callCardTerminalStatusApi() {
  // 카드 터미널 상태 - 현재 미구현, 기본값 반환
  return '39';
}

async function callIOStatusApi() {
  try {
    const response = await axios.get(`${IO_BOARD_API_URL}/status`, {
      timeout: 5000
    });

    // door: OPEN/CLOSED, deadbolt: OPEN/LOCKED
    if (response.data.door === 'CLOSED' && response.data.deadbolt === 'LOCKED') {
      return '19'; // 정상 상태
    } else {
      return '20'; // 이상 상태 (문 열림 또는 데드볼트 열림)
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

    // health publish interval (1분마다)
    setInterval(async () => {
      const timestamp = Date.now();

      // 상태 조회
      const apiDeadboltStatus = await callIOStatusApi();
      const apiCardTerminalStatus = await callCardTerminalStatusApi();
      const apiLoadcellStatus = "29"; // 현재 미구현
      const apiCameraStatus = "09"; // 현재 미구현

      // IO 보드 전체 상태
      const IOBoardStatus = (apiDeadboltStatus === "19" && apiLoadcellStatus === "29") ? "49" : "41";

      const header = {
        IF_ID: "IF_02",
        IF_SYSID: uuidv4(),
        IF_HOST: "MQTTX",
        IF_DATE: timestamp,
      };

      const body = {
        device_idx: deviceIdx,
        division_idx: divisionIdx,
        camera_status: apiCameraStatus,
        deadbolt_status: apiDeadboltStatus,
        loadcell_status: apiLoadcellStatus,
        card_terminal_status: apiCardTerminalStatus,
        ioboard_status: IOBoardStatus,
        edgepc_status: '49'
      };

      const payload = JSON.stringify({ HEADER: header, DATA: body });
      console.log('[HealthMqtt] Publishing:', payload);

      client.publish(healthCheck, payload, { qos: 0, retain: false }, (e) => {
        if (e) console.error("[MQTT] publish error:", e.message);
      });
    }, 60000);
  });
}

module.exports = { HealthMqtt, callCardTerminalStatusApi, callIOStatusApi };
