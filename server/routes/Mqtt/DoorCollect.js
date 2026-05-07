// server/routes/Mqtt/DoorCollect.js
const { v4: uuidv4 } = require("uuid");
const { EventSource } = require("eventsource");

const config = require("../../config/key");
const { callApiToControlDeadbolt } = require("./DeadboltApiService");
const {
  DeadboltStatusAPI,
  LoadcellStatusAPI,
  CameraStatusAPI,
} = require("./HealthMqtt");
const { getClient } = require("./MqttClient");

function makeIFDate(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}${HH}${MM}${SS}`;
}

function makeAckPayload({
  reqStorageType,
  reqHasLoadCell,
  doorState,
  resultCd = "S",
  resultMsg = "success",
  extraData = {},
}) {
  return {
    HEADER: {
      IF_ID: "IF_04",
      IF_SYSID: uuidv4(),
      IF_HOST: "CRKPNTCCHAI",
      IF_DATE: makeIFDate(),
    },
    DATA: {
      division_idx: config.divisionIdx,
      device_idx: config.deviceIdx,
      door_state: doorState,
      storage_type: reqStorageType ?? null,
      has_loadcell: reqHasLoadCell ?? null,
      result_cd: resultCd,
      result_msg: resultMsg,
      ...extraData,
    },
  };
}

function publishAck(client, topic, payload) {
  if (!client || !client.connected) {
    console.error("[DoorCollect] MQTT client is not connected. Cannot publish ACK.");
    return;
  }

  client.publish(topic, JSON.stringify(payload), (err) => {
    if (err) {
      console.error("[DoorCollect] ACK publish failed:", err);
    }
  });
}

async function fetchCurrentDoorState() {
  return new Promise((resolve) => {
    const url = `${config.ioboardApi}/sse?streams=doors`;

    let evtSource;

    try {
      evtSource = new EventSource(url);
    } catch (err) {
      console.error("[DoorCheck] EventSource create failed:", err.message);
      resolve("UNKNOWN");
      return;
    }

    const timeout = setTimeout(() => {
      evtSource.close();
      console.warn("[DoorCheck] Timeout");
      resolve("UNKNOWN");
    }, 3000);

    evtSource.addEventListener("door.update", (event) => {
      if (!event.data) return;

      try {
        const data = JSON.parse(event.data);
        const rawState = data.deadbolt ? String(data.deadbolt).toUpperCase() : "";
        const closedStates = ["LOCK", "LOCKED", "CLOSE", "CLOSED"];
        const finalState = closedStates.includes(rawState) ? "CLOSE" : "OPEN";

        clearTimeout(timeout);
        evtSource.close();
        resolve(finalState);
      } catch (err) {
        clearTimeout(timeout);
        evtSource.close();
        resolve("UNKNOWN");
      }
    });

    evtSource.onerror = () => {
      clearTimeout(timeout);
      evtSource.close();
      resolve("UNKNOWN");
    };
  });
}

async function ProductCollectionHealth() {
  const CameraStatus = await CameraStatusAPI();
  const DeadboltHealth = await DeadboltStatusAPI();
  const LoadcellHealth = await LoadcellStatusAPI();
  const CurrentDoorState = await fetchCurrentDoorState();

  const isHealthOk =
    CameraStatus === "09" &&
    DeadboltHealth === "19" &&
    LoadcellHealth === "29";

  return {
    CameraStatus,
    DeadboltHealth,
    LoadcellHealth,
    CurrentDoorState,
    isSuccess: isHealthOk,
    resultMsg: isHealthOk ? "status access" : "status error",
  };
}

async function handleOpen({
  client,
  ackTopic,
  reqStorageType,
  reqHasLoadCell,
}) {
  const currentDoorState = await fetchCurrentDoorState();

  if (currentDoorState !== "CLOSE") {
    throw new Error("현재 문이 열려있는 상태입니다.");
  }

  const openResult = await callApiToControlDeadbolt("OPEN");
  console.log("[DoorCollect] deadbolt open result:", openResult);

  const health = await ProductCollectionHealth();

  const ackPayload = makeAckPayload({
    reqStorageType,
    reqHasLoadCell,
    doorState: health.CurrentDoorState,
    resultCd: health.isSuccess ? "S" : "F",
    resultMsg: health.resultMsg,
    extraData: {
      camera_status: health.CameraStatus === "09" ? "1" : "0",
      deadbolt_status: health.DeadboltHealth === "19" ? "1" : "0",
      loadcell_status: health.LoadcellHealth === "29" ? "1" : "0",
    },
  });

  publishAck(client, ackTopic, ackPayload);
}

async function handleClose({
  client,
  ackTopic,
  reqStorageType,
  reqHasLoadCell,
}) {
  const currentDoorState = await fetchCurrentDoorState();

  if (currentDoorState !== "CLOSE") {
    throw new Error("문이 아직 닫히지 않았습니다.");
  }

  const closeResult = await callApiToControlDeadbolt("CLOSE").catch((err) => {
    console.warn("[DoorCollect] deadbolt close warning:", err.message);
    return null;
  });

  console.log("[DoorCollect] deadbolt close result:", closeResult);

  const health = await ProductCollectionHealth();

  const ackPayload = makeAckPayload({
    reqStorageType,
    reqHasLoadCell,
    doorState: health.CurrentDoorState,
    resultCd: health.isSuccess ? "S" : "F",
    resultMsg: health.resultMsg,
    extraData: {
      camera_status: health.CameraStatus === "09" ? "1" : "0",
      deadbolt_status: health.DeadboltHealth === "19" ? "1" : "0",
      loadcell_status: health.LoadcellHealth === "29" ? "1" : "0",
    },
  });

  publishAck(client, ackTopic, ackPayload);
}

async function DoorCollect() {
  const DoorCollect_SUB_TOPIC = `chai/device/${config.deviceIdx}/cmd/door/collect`;
  const DoorCollect_PUB_TOPIC = `chai/device/${config.deviceIdx}/ack/door/collect`;

  const client = getClient();

  client.on("connect", () => {
    client.subscribe(DoorCollect_SUB_TOPIC, (err) => {
      if (err) {
        console.error("[DoorCollect] MQTT subscribe failed:", err);

        const errorPayload = makeAckPayload({
          reqStorageType: null,
          reqHasLoadCell: null,
          doorState: "UNKNOWN",
          resultCd: "F",
          resultMsg: `MQTT subscribe failed: ${err.message}`,
        });

        publishAck(client, DoorCollect_PUB_TOPIC, errorPayload);
        return;
      }

      console.log(`[DoorCollect] subscribed: ${DoorCollect_SUB_TOPIC}`);
    });
  });

  client.on("message", async (topic, message) => {
    if (topic !== DoorCollect_SUB_TOPIC) return;

    let reqData = {};

    try {
      const payload = JSON.parse(message.toString());
      reqData = payload.DATA || {};

      const reqDoorState = reqData.door_state;
      const reqStorageType = reqData.storage_type;
      const reqHasLoadCell = reqData.has_loadcell;

      const targetId = topic.split("/")[2];
      if (targetId !== config.deviceIdx && targetId !== "+") return;

      console.log(`[DoorCollect] Request Received: ${reqDoorState}`);

      if (reqDoorState === "OPEN") {
        await handleOpen({
          client,
          ackTopic: DoorCollect_PUB_TOPIC,
          reqStorageType,
          reqHasLoadCell,
        });
        return;
      }

      if (reqDoorState === "CLOSE") {
        await handleClose({
          client,
          ackTopic: DoorCollect_PUB_TOPIC,
          reqStorageType,
          reqHasLoadCell,
        });
        return;
      }

      throw new Error(`Unsupported door_state: ${reqDoorState}`);
    } catch (error) {
      console.error("[DoorCollect] Processing Error:", error);

      const errorPayload = makeAckPayload({
        reqStorageType: reqData.storage_type,
        reqHasLoadCell: reqData.has_loadcell,
        doorState: reqData.door_state || "UNKNOWN",
        resultCd: "F",
        resultMsg: error?.message || String(error),
      });

      publishAck(client, DoorCollect_PUB_TOPIC, errorPayload);
    }
  });

  client.on("error", (err) => {
    console.error("[DoorCollect] MQTT client error:", err);
  });

  client.on("close", () => {
    console.warn("[DoorCollect] MQTT client closed");
  });
}

module.exports = {
  DoorCollect,
  fetchCurrentDoorState,
  ProductCollectionHealth,
};