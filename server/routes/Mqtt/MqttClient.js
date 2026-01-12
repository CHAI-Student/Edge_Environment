const mqtt = require("mqtt");
const config = require("../../config/key");

let client = null;

function createMqttClient() {
  if (!config.mqttURL) throw new Error("Missing config.mqttURL");
  if (!config.mqttID) throw new Error("Missing config.mqttID");
  if (!config.mqttPW) throw new Error("Missing config.mqttPW");

  const clientId = `edge-logic-${config.divisionIdx || "x"}-${Math.random()
    .toString(16)
    .slice(2)}`;

  // ⚠️ broker가 사설 인증서(TLS)라서 self-signed 이면 rejectUnauthorized:false가 필요할 수 있음(테스트 용도)
  const options = {
    clientId,
    username: config.mqttID,
    password: config.mqttPW,

    clean: true,
    keepalive: 30,
    connectTimeout: 8000,

    // 재연결 주기(ms). 운영에선 1000~5000 정도 권장
    reconnectPeriod: 2000,

    // TLS 관련 필요 시:
    // rejectUnauthorized: true,
  };

  client = mqtt.connect(config.mqttURL, options);

  client.on("connect", () => {
    console.log(`[MQTT] ✅ connected (${config.mqttURL}) clientId=${clientId}`);
  });

  client.on("reconnect", () => {
    console.log("[MQTT] 🔄 reconnecting...");
  });

  client.on("offline", () => {
    console.log("[MQTT] ⚠️ offline");
  });

  client.on("close", () => {
    console.log("[MQTT] ℹ️ connection closed");
  });

  client.on("error", (err) => {
    console.error("[MQTT] ⛔ error:", err?.message || err);
    // error 이벤트만으로는 자동 종료 안 하니, 필요한 경우 여기서 정책 처리
  });
  client.on("disconnect", (packet) => {
    console.log("[MQTT] ⚠️ disconnect packet:", packet);
  });
  client.on("end", () => {
    console.log("[MQTT] ℹ️ end");
  });


  // 메시지 수신은 여기서 공통 핸들링
  client.on("message", (topic, payload, packet) => {
    const msg = payload.toString();
    console.log(`[MQTT] 📩 topic=${topic} payload=${msg}`);

    // TODO: 여기서 topic별 라우팅/모델 호출/DB 저장 등 연결 가능
    // handleIncomingMessage(topic, msg, packet);
  });

  return client;
}

function getClient() {
  if (!client) return createMqttClient();
  return client;
}

function subscribe(topics) {
  const c = getClient();
  const list = Array.isArray(topics) ? topics : [topics];

  return new Promise((resolve, reject) => {
    // QoS는 요구사항에 맞게 조절 (0/1/2)
    c.subscribe(list, { qos: 0 }, (err, granted) => {
      if (err) return reject(err);
      console.log("[MQTT] ✅ subscribed:", granted);
      resolve(granted);
    });
  });
}

function publish(topic, payload, opts = {}) {
  const c = getClient();
  const message = typeof payload === "string" ? payload : JSON.stringify(payload);

  const options = {
    qos: opts.qos ?? 0,
    retain: opts.retain ?? false,
  };

  return new Promise((resolve, reject) => {
    c.publish(topic, message, options, (err) => {
      if (err) return reject(err);
      resolve(true);
    });
  });
}

function disconnect() {
  if (!client) return Promise.resolve(true);

  return new Promise((resolve) => {
    client.end(true, () => {
      console.log("[MQTT] ✅ disconnected");
      client = null;
      resolve(true);
    });
  });
}

module.exports = {
  getClient,
  subscribe,
  publish,
  disconnect,
};
