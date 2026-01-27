const config = require("../../config/key");
const { getClient } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const axios = require("axios");

const PAYMENT_API = config.cameraApi; 
const PAYMENT_STATUS_ENDPOINT = 'status';

async function callCardTerminalStatusApi() {
  const PAYMENT_API_URL = `${PAYMENT_API}/${PAYMENT_STATUS_ENDPOINT}`;
  try {
    // console.log(`[API] Checking Status: ${PAYMENT_API_URL}`);
    const response = await axios.get(PAYMENT_API_URL, {
      timeout: 5000 
    });

    if (response.data && response.data.status === "ok") { 
      return '39'; // 정상 (Connected)
    } else {
      return '41'; // 비정상
    }

  } catch (error) {
    console.error(`[API Error] Card Terminal Check Failed: ${error.message}`);
    return '41';
  }
}

async function HealthMqtt() {
  const deviceIdx = config.deviceIdx;
  const divisionIdx = config.divisionIdx;
  
  // publish 토픽 설정
  const healthCheck = `chai/device/${deviceIdx}/health`;

  const client = getClient();
  client.on("connect", () => {
    console.log("[MQTT] connected");
    
    // 60초마다 반복
    setInterval(async () => {
      const timestamp = Date.now();

      const apiLoadcellStatus = "29";
      const apiCameraStatus = "09";
      const apiDeadboltStatus = '19';
      const apiCardTerminalStatus = await callCardTerminalStatusApi();

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
        CardTerminalStatus: apiCardTerminalStatus, // 최신 상태값 전송
      };

      const payload = JSON.stringify({ HEADER: header, DATA: body });
      
      // 로그에 현재 단말기 상태 코드 출력
      console.log(`[Health Check] Terminal: ${apiCardTerminalStatus}, Payload sent.`);

      client.publish(healthCheck, payload, { qos: 0, retain: false }, (e) => {
        if (e) console.error("[MQTT] publish error:", e.message);
      });
    }, 60000);
  });

  return apiLoadcellStatus, apiCameraStatus, apiCardTerminalStatus, apiDeadboltStatus
}

module.exports = { HealthMqtt };