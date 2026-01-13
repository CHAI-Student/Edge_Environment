const config = require("../../config/key");
const { getClient, subscribe } = require("./MqttClient");
const { v4: uuidv4 } = require("uuid");
const path = require("path");
const fs = require("fs/promises");

console.log(path.join(__dirname))

const REBOOT_FLAG = path.join(__dirname, "..", "reboot.flag"); // 위치는 편한 곳으로

async function RebootMqtt() {
  // divisionIdx 기준으로 토픽 네이밍 예시
    const deviceIdx = config.deviceIdx
    const divisionIdx = config.divisionIdx
  
    const rebootPub = `chai/device/${deviceIdx}/ack/reboot` // reboot 후 subscribe 발행
    
    // subscribe
    const rebootSub = `chai/device/${deviceIdx}/cmd/reboot`
  
    const client = getClient(); // 연결 시작
    client.on("connect", () => {
      console.log("[MQTT] connected");
  
      // ✅ subscribe
      client.subscribe(topics, { qos: 0 }, (err, granted) => {
        if (err) console.error("[MQTT] subscribe error:", err.message);
        else console.log("[MQTT] subscribed:", granted);
      });
  
      // ✅ health publish interval (connect 이후 시작)
      setInterval(() => {
        const timestamp = Date.now();
  
        const header = {
          IF_ID: "IF_01",
          IF_SYSID: uuidv4(),
          IF_HOST: "DEVICE",
          IF_DATE: timestamp,
        };
  
        const body = {
          device_idx: deviceIdx,
          division_idx: divisionIdx,
          result: 'S',
          message: 'reboot accepted'
        };
  
        const payload = JSON.stringify({ HEADER: header, DATA: body });
        console.log('Reboot ----> ', payload)
  
        client.publish(rebootPub, payload, { qos: 0, retain: false }, (e) => {
          if (e) console.error("[MQTT] publish error:", e.message);
        });
      }, 10000);
    });
  
    // ✅ subscribe 메시지 핸들링
    client.on("message", (topic, payload) => {
      const msg = payload.toString();
      console.log("[MQTT] message", topic, msg);
  
      // TODO: topic별 처리
      // if (topic.endsWith("/cmd/reboot")) ...
    });

}

module.exports = { RebootMqtt };