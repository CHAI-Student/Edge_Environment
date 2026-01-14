const { v4: uuidv4 } = require("uuid");
const { getClient } = require("./MqttClient");
const config = require("../../config/key");

async function ManualDoor() {
  const deviceIdx = config.deviceIdx;
  const divisionIdx = config.divisionIdx;

  if (!deviceIdx || !divisionIdx) {
    console.error("[DOOR] Missing deviceIdx/divisionIdx in config");
    return;
  }

  const manualDoorSub = `chai/device/${deviceIdx}/cmd/door/manual`;
  const manualDoorPub = `chai/device/${deviceIdx}/ack/door/manual`;

  const client = getClient();

  // ✅ connect 로그(참고용)
  client.on("connect", () => {
    console.log("[DOOR] connected");
    client.subscribe(manualDoorSub, { qos: 1 }, (err, granted) => {
      if (err) console.error("[DOOR] subscribe error:", err.message);
      else console.log("[DOOR] subscribed:", granted);
    });
  });

  // ✅ cmd 수신 → ack 발행
  client.on("message", (topic, payloadBuf) => {
    if (topic !== manualDoorSub) return;

    let msg;
    try {
      msg = JSON.parse(payloadBuf.toString());
    } catch (e) {
      console.error("[DOOR] invalid JSON:", payloadBuf.toString());
      return;
    }

    const doorState = msg?.DATA?.door_state; // 'OPEN' or 'CLOSE'
    const ifSysId = msg?.HEADER?.IF_SYSID || uuidv4();

    console.log("[DOOR] cmd received. IF_SYSID=", ifSysId, "doorState=", doorState);

    if (doorState !== "OPEN" && doorState !== "CLOSE") {
      console.error("[DOOR] invalid door_state:", doorState);
      return;
    }

    const nextState = doorState === "OPEN" ? "CLOSE" : "OPEN";
    const timestamp = Date.now();

    const header = {
      IF_ID: "IF_03",
      IF_SYSID: ifSysId,     // ✅ cmd의 IF_SYSID 그대로 echo
      IF_HOST: "CHAI",
      IF_DATE: timestamp,
    };

    const body = {
      device_idx: deviceIdx,
      division_idx: divisionIdx,
      door_state: nextState,
      result_cd: "S",
      result_msg: doorState === "OPEN" ? "Door is closed" : "Door is opened",
    };

    const ackPayload = JSON.stringify({ HEADER: header, DATA: body });

    client.publish(manualDoorPub, ackPayload, { qos: 1, retain: false }, (e) => {
      if (e) console.error("[DOOR] publish error:", e.message);
      else console.log("[DOOR] ack published:", manualDoorPub, "IF_SYSID=", ifSysId);
    });
  });

  // ✅ 이미 연결되어 있으면 수동 subscribe (connect 이벤트 놓침 대비)
  if (client.connected) {
    client.subscribe(manualDoorSub, { qos: 1 }, (err, granted) => {
      if (err) console.error("[DOOR] subscribe error:", err.message);
      else console.log("[DOOR] subscribed:", granted);
    });
  }
}

module.exports = { ManualDoor };
