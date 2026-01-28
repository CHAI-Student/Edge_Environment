const mqtt = require("mqtt");
const config = require("../../config/key");

let client = null;

function createMqttClient() {
  if (!config.mqttURL) throw new Error("Missing config.mqttURL");
  if (!config.mqttID) throw new Error("Missing config.mqttID");
  if (!config.mqttPW) throw new Error("Missing config.mqttPW");

  const deviceIdx = config.deviceIdx

  const clientId = deviceIdx

  // broker가 사설 인증서(TLS)라서 self-signed 이면 rejectUnauthorized:false가 필요할 수 있음(테스트 용도)
  const options = {
    clientId,
    username: config.mqttID,
    password: config.mqttPW,
    clean: true,
    keepalive: 30,
    connectTimeout: 10000,

    // 재연결 주기(ms). 운영에선 1000~5000 정도 권장
    reconnectPeriod: 2000,

    // TLS 관련 필요 시:
    // rejectUnauthorized: true,
  };

  client = mqtt.connect(config.mqttURL, options);

  client.on("connect", () => {
    console.log(`[MQTT] connected (${config.mqttURL}) clientId=${clientId}`);
  });
  client.on("reconnect", () => console.log("[MQTT] reconnecting..."));
  client.on("offline", () => console.log("[MQTT] offline"));
  client.on("close", () => console.log("[MQTT] close"));
  client.on("end", () => console.log("[MQTT] end"));
  client.on("error", (err) => console.error("[MQTT] error:", err?.message || err));

  // 공통 수신 로깅(원하면 여기서 topic 라우팅도 가능)
  client.on("message", (topic, payload) => {
    console.log(`[MQTT] topic=${topic} payload=${payload.toString()}`);
  });

  return client;
}

function getClient() {
  if (!client) return createMqttClient();
  return client;
}

function waitForConnect(c, timeoutMs = 8000) {
  if (c.connected) return Promise.resolve(true);

  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("MQTT connect timeout")), timeoutMs);

    c.once("connect", () => {
      clearTimeout(t);
      resolve(true);
    });
    c.once("error", (e) => {
      clearTimeout(t);
      reject(e);
    });
  });
}

async function subscribe(topics, qos = 0) {
  const c = getClient();
  const list = Array.isArray(topics) ? topics : [topics];

  await waitForConnect(c); // 연결 보장

  return new Promise((resolve, reject) => {
    // QoS는 요구사항에 맞게 조절 (0/1/2)
    c.subscribe(list, { qos: 0 }, (err, granted) => {
      if (err) return reject(err);
      console.log("[MQTT] subscribed:", granted);
      resolve(granted);
    });
  });
}

function publish(topic, payload, opts = {}) {
  const c = getClient();
  const message = typeof payload === "string" ? payload : JSON.stringify(payload);

  const options = {
    qos: 1,
    retain: false,
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
      console.log("[MQTT] disconnected");
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