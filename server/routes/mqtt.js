require("dotenv").config();

const express = require("express");
const { HealthMqtt } = require("./Mqtt/HealthMqtt");
const { publish } = require("./Mqtt/MqttClient");

const router = express.Router();
router.use(express.json({ limit: "1mb" }));

// REST -> MQTT publish 예시
router.post("/api/publish", async (req, res) => {
  try {
    const { topic, payload, qos, retain } = req.body;
    if (!topic) return res.status(400).json({ error: "topic is required" });

    await publish(topic, payload ?? {}, { qos, retain });
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: e?.message || String(e) });
  }
});

// HealthMqtt는 서버 시작 시 호출
async function init() {
  try {
    await HealthMqtt();
    console.log("[APP] MQTT init done");
  } catch (e) {
    console.error("[APP] MQTT init failed:", e?.message || e);
    throw e;
  }
}

module.exports = {
  router,
  init,
};