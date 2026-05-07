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

function normalizeHealthStatus(raw, okCode, hasDevice = true) {
  // 정의서상 status size가 1이고, 로드셀이 없는 경우 9 전달 가능
  if (!hasDevice) return "9";
  return raw === okCode ? "1" : "0";
}

function makeAckPayload({
  reqDeviceIdx = config.deviceIdx,
  reqDivisionIdx = config.divisionIdx,
  reqStorageType,
  reqHasLoadCell,
  doorState,
  cameraStatus = "0",
  deadboltStatus = "0",
  loadcellStatus = "0",
  resultCd = "S",
  resultMsg = "success",
}) {
  return {
    HEADER: {
      IF_ID: "IF_04",
      IF_SYSID: uuidv4(),
      IF_HOST: "CRKPNTCCHAI",
      IF_DATE: makeIFDate(),
    },
    DATA: {
      device_idx: reqDeviceIdx,
      division_idx: reqDivisionIdx,
      door_state: doorState,
      storage_type: reqStorageType ?? null,
      has_loadcell: reqHasLoadCell ?? null,
      camera_status: cameraStatus,
      deadbolt_status: deadboltStatus,
      loadcell_status: loadcellStatus,
      result_cd: resultCd,
      result_msg: resultMsg,
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
    } else {
      console.log(`[DoorCollect] ACK published: ${payload.DATA.door_state}, ${payload.DATA.result_cd}`);
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
        const openStates = ["UNLOCK", "UNLOCKED", "OPEN", "OPENED"];

        let finalState = "UNKNOWN";

        if (closedStates.includes(rawState)) finalState = "CLOSE";
        else if (openStates.includes(rawState)) finalState = "OPEN";
        else finalState = closedStates.includes(rawState) ? "CLOSE" : "OPEN";

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

async function waitForDoorState(targetState, { timeoutMs = 5000, intervalMs = 300 } = {}) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const state = await fetchCurrentDoorState();

    if (state === targetState) {
      return state;
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  return await fetchCurrentDoorState();
}

async function ProductCollectionHealth(reqHasLoadCell) {
  const CameraStatus = await CameraStatusAPI();
  const DeadboltHealth = await DeadboltStatusAPI();

  const hasLoadcell =
    reqHasLoadCell === true ||
    reqHasLoadCell === "Y" ||
    reqHasLoadCell === "1" ||
    reqHasLoadCell === 1;

  let LoadcellHealth = "29";

  if (hasLoadcell) {
    LoadcellHealth = await LoadcellStatusAPI();
  }

  const CurrentDoorState = await fetchCurrentDoorState();

  const camera_status = normalizeHealthStatus(CameraStatus, "09", true);
  const deadbolt_status = normalizeHealthStatus(DeadboltHealth, "19", true);
  const loadcell_status = normalizeHealthStatus(LoadcellHealth, "29", hasLoadcell);

  const isHealthOk =
    camera_status === "1" &&
    deadbolt_status === "1" &&
    (hasLoadcell ? loadcell_status === "1" : true);

  return {
    CameraStatus,
    DeadboltHealth,
    LoadcellHealth,
    CurrentDoorState,
    camera_status,
    deadbolt_status,
    loadcell_status,
    isSuccess: isHealthOk,
    resultMsg: isHealthOk ? "status access" : "status error",
  };
}

function validateRequestDevice(reqData) {
  const reqDeviceIdx = reqData.device_idx;
  const reqDivisionIdx = reqData.division_idx;

  if (String(reqDeviceIdx) !== String(config.deviceIdx)) {
    throw new Error(`Invalid device_idx: ${reqDeviceIdx}`);
  }

  if (String(reqDivisionIdx) !== String(config.divisionIdx)) {
    throw new Error(`Invalid division_idx: ${reqDivisionIdx}`);
  }
}

async function handleOpen({
  client,
  ackTopic,
  reqData,
}) {
  const reqDeviceIdx = reqData.device_idx;
  const reqDivisionIdx = reqData.division_idx;
  const reqStorageType = reqData.storage_type;
  const reqHasLoadCell = reqData.has_loadcell;

  validateRequestDevice(reqData);

  const beforeState = await fetchCurrentDoorState();

  if (beforeState === "OPEN") {
    const health = await ProductCollectionHealth(reqHasLoadCell);

    const ackPayload = makeAckPayload({
      reqDeviceIdx,
      reqDivisionIdx,
      reqStorageType,
      reqHasLoadCell,
      doorState: "OPEN",
      cameraStatus: health.camera_status,
      deadboltStatus: health.deadbolt_status,
      loadcellStatus: health.loadcell_status,
      resultCd: "S",
      resultMsg: "door already opened",
    });

    publishAck(client, ackTopic, ackPayload);
    return;
  }

  const openResult = await callApiToControlDeadbolt("OPEN");
  console.log("[DoorCollect] deadbolt open result:", openResult);

  const finalDoorState = await waitForDoorState("OPEN", {
    timeoutMs: 5000,
    intervalMs: 300,
  });

  const health = await ProductCollectionHealth(reqHasLoadCell);

  const isOpenSuccess = finalDoorState === "OPEN";

  const ackPayload = makeAckPayload({
    reqDeviceIdx,
    reqDivisionIdx,
    reqStorageType,
    reqHasLoadCell,
    doorState: finalDoorState,
    cameraStatus: health.camera_status,
    deadboltStatus: health.deadbolt_status,
    loadcellStatus: health.loadcell_status,
    resultCd: isOpenSuccess && health.isSuccess ? "S" : "F",
    resultMsg: isOpenSuccess
      ? health.resultMsg
      : `door open command sent, but current state is ${finalDoorState}`,
  });

  publishAck(client, ackTopic, ackPayload);
}

async function handleClose({
  client,
  ackTopic,
  reqData,
}) {
  const reqDeviceIdx = reqData.device_idx;
  const reqDivisionIdx = reqData.division_idx;
  const reqStorageType = reqData.storage_type;
  const reqHasLoadCell = reqData.has_loadcell;

  validateRequestDevice(reqData);

  const beforeState = await fetchCurrentDoorState();

  if (beforeState !== "CLOSE") {
    const closeResult = await callApiToControlDeadbolt("CLOSE").catch((err) => {
      console.warn("[DoorCollect] deadbolt close warning:", err.message);
      return null;
    });

    console.log("[DoorCollect] deadbolt close result:", closeResult);
  }

  const finalDoorState = await waitForDoorState("CLOSE", {
    timeoutMs: 5000,
    intervalMs: 300,
  });

  const health = await ProductCollectionHealth(reqHasLoadCell);

  const isCloseSuccess = finalDoorState === "CLOSE";

  const ackPayload = makeAckPayload({
    reqDeviceIdx,
    reqDivisionIdx,
    reqStorageType,
    reqHasLoadCell,
    doorState: finalDoorState,
    cameraStatus: health.camera_status,
    deadboltStatus: health.deadbolt_status,
    loadcellStatus: health.loadcell_status,
    resultCd: isCloseSuccess && health.isSuccess ? "S" : "F",
    resultMsg: isCloseSuccess
      ? health.resultMsg
      : `door close command sent, but current state is ${finalDoorState}`,
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

      console.log(`[DoorCollect] Request Received: ${reqDoorState}`);

      if (reqDoorState === "OPEN") {
        await handleOpen({
          client,
          ackTopic: DoorCollect_PUB_TOPIC,
          reqData,
        });
        return;
      }

      if (reqDoorState === "CLOSE") {
        await handleClose({
          client,
          ackTopic: DoorCollect_PUB_TOPIC,
          reqData,
        });
        return;
      }

      throw new Error(`Unsupported door_state: ${reqDoorState}`);
    } catch (error) {
      console.error("[DoorCollect] Processing Error:", error);

      const health = await ProductCollectionHealth(reqData.has_loadcell).catch(() => ({
        camera_status: "0",
        deadbolt_status: "0",
        loadcell_status: "0",
      }));

      const errorPayload = makeAckPayload({
        reqDeviceIdx: reqData.device_idx || config.deviceIdx,
        reqDivisionIdx: reqData.division_idx || config.divisionIdx,
        reqStorageType: reqData.storage_type,
        reqHasLoadCell: reqData.has_loadcell,
        doorState: reqData.door_state || "UNKNOWN",
        cameraStatus: health.camera_status,
        deadboltStatus: health.deadbolt_status,
        loadcellStatus: health.loadcell_status,
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