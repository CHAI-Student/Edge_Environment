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

async function fetchCurrentDoorState() {
  return new Promise((resolve) => {
    const url = `${config.ioboardApi}/sse?streams=doors`;

    let evtSource;
    try {
      evtSource = new EventSource(url);
    } catch (err) {
      console.error("[DoorCollect] EventSource Error:", err.message);
      resolve("UNKNOWN");
      return;
    }

    const timer = setTimeout(() => {
      evtSource.close();
      resolve("UNKNOWN");
    }, 3000);

    evtSource.addEventListener("door.update", (event) => {
      try {
        const data = JSON.parse(event.data || "{}");
        const raw = String(data.deadbolt || "").toUpperCase();

        const closeStates = ["LOCK", "LOCKED", "CLOSE", "CLOSED"];
        const openStates = ["UNLOCK", "UNLOCKED", "OPEN", "OPENED"];

        let state = "UNKNOWN";
        if (closeStates.includes(raw)) state = "CLOSE";
        if (openStates.includes(raw)) state = "OPEN";

        clearTimeout(timer);
        evtSource.close();
        resolve(state);
      } catch {
        clearTimeout(timer);
        evtSource.close();
        resolve("UNKNOWN");
      }
    });

    evtSource.onerror = () => {
      clearTimeout(timer);
      evtSource.close();
      resolve("UNKNOWN");
    };
  });
}

async function waitForDoorState(targetState, timeoutMs = 5000) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const state = await fetchCurrentDoorState();

    if (state === targetState) return state;

    await new Promise((resolve) => setTimeout(resolve, 300));
  }

  return await fetchCurrentDoorState();
}

async function getHealthStatus(hasLoadcell) {
  const cameraRaw = await CameraStatusAPI();
  const deadboltRaw = await DeadboltStatusAPI();

  const useLoadcell =
    hasLoadcell === "Y" ||
    hasLoadcell === "1" ||
    hasLoadcell === true ||
    hasLoadcell === 1;

  let loadcellRaw = "29";

  if (useLoadcell) {
    loadcellRaw = await LoadcellStatusAPI();
  }

  return {
    camera_status: cameraRaw === "09" ? "1" : "0",
    deadbolt_status: deadboltRaw === "19" ? "1" : "0",
    loadcell_status: useLoadcell ? (loadcellRaw === "29" ? "1" : "0") : "9",
  };
}

function publishDoorAck({
  client,
  topic,
  ifSysId,
  deviceIdx,
  divisionIdx,
  doorState,
  storageType,
  hasLoadcell,
  cameraStatus,
  deadboltStatus,
  loadcellStatus,
  resultCd,
  resultMsg,
}) {
  const ackPayload = JSON.stringify({
    HEADER: {
      IF_ID: "IF_04",
      IF_SYSID: ifSysId || uuidv4(),
      IF_HOST: "CRKPNTCCHAI",
      IF_DATE: makeIFDate(),
    },
    DATA: {
      device_idx: deviceIdx,
      division_idx: divisionIdx,
      door_state: doorState,
      storage_type: storageType,
      has_loadcell: hasLoadcell,
      camera_status: cameraStatus,
      deadbolt_status: deadboltStatus,
      loadcell_status: loadcellStatus,
      result_cd: resultCd,
      result_msg: resultMsg,
    },
  });

  console.log("[DoorCollect] PUB Topic:", topic);
  console.log("[DoorCollect] PUB Payload:", ackPayload);

  client.publish(topic, ackPayload, { qos: 1, retain: false }, (e) => {
    if (e) {
      console.error("[DoorCollect] Publish Error:", e.message);
    } else {
      console.log(
        `[DoorCollect] ACK Sent. Result=${resultCd}, State=${doorState}`
      );
    }
  });
}

async function DoorCollect() {
  const subTopic = `chai/device/${config.deviceIdx}/cmd/door/collect`;
  const pubTopic = `chai/device/${config.deviceIdx}/ack/door/collect`;

  const client = getClient();

  client.on("connect", () => {
    client.subscribe(subTopic, { qos: 1 }, (err) => {
      if (err) {
        console.error("[DoorCollect] Subscribe Error:", err.message);

        publishDoorAck({
          client,
          topic: pubTopic,
          ifSysId: uuidv4(),
          deviceIdx: config.deviceIdx,
          divisionIdx: config.divisionIdx,
          doorState: "UNKNOWN",
          storageType: null,
          hasLoadcell: null,
          cameraStatus: "0",
          deadboltStatus: "0",
          loadcellStatus: "0",
          resultCd: "F",
          resultMsg: `Subscribe Error: ${err.message}`,
        });

        return;
      }

      console.log(`[DoorCollect] Subscribed: ${subTopic}`);
    });
  });

  client.on("message", async (topic, message) => {
    if (topic !== subTopic) return;

    let reqData = {};
    let ifSysId = uuidv4();

    try {
      const payload = JSON.parse(message.toString());
      ifSysId = payload.HEADER?.IF_SYSID || uuidv4();
      reqData = payload.DATA || {};

      const {
        device_idx: deviceIdx,
        division_idx: divisionIdx,
        door_state: reqDoorState,
        storage_type: storageType,
        has_loadcell: hasLoadcell,
      } = reqData;

      console.log("[DoorCollect] Request:", reqData);
      
      await callApiToControlDeadbolt(reqDoorState);

      const finalState = await waitForDoorState(reqDoorState, 5000);
      const health = await getHealthStatus(hasLoadcell);

      const isDoorOk = finalState === reqDoorState;
      const isHealthOk =
        health.camera_status === "1" &&
        health.deadbolt_status === "1" &&
        (health.loadcell_status === "1" || health.loadcell_status === "9");

      const resultCd = isDoorOk && isHealthOk ? "S" : "F";
      const resultMsg =
        resultCd === "S"
          ? "status access"
          : `door=${finalState}, camera=${health.camera_status}, deadbolt=${health.deadbolt_status}, loadcell=${health.loadcell_status}`;

      publishDoorAck({
        client,
        topic: pubTopic,
        ifSysId,
        deviceIdx,
        divisionIdx,
        doorState: finalState,
        storageType,
        hasLoadcell,
        cameraStatus: health.camera_status,
        deadboltStatus: health.deadbolt_status,
        loadcellStatus: health.loadcell_status,
        resultCd,
        resultMsg,
      });
    } catch (error) {
      console.error("[DoorCollect] Error:", error.message);

      const health = await getHealthStatus(reqData.has_loadcell).catch(() => ({
        camera_status: "0",
        deadbolt_status: "0",
        loadcell_status: "0",
      }));

      publishDoorAck({
        client,
        topic: pubTopic,
        ifSysId,
        deviceIdx: config.deviceIdx,
        divisionIdx: config.divisionIdx,
        doorState: reqData.door_state,
        storageType: reqData.storage_type,
        hasLoadcell: reqData.has_loadcell,
        cameraStatus: health.camera_status,
        deadboltStatus: health.deadbolt_status,
        loadcellStatus: health.loadcell_status,
        resultCd: "F",
        resultMsg: error?.message || String(error),
      });
    }
  });

  client.on("error", (err) => {
    console.error("[DoorCollect] MQTT Error:", err.message);
  });

  client.on("close", () => {
    console.warn("[DoorCollect] MQTT Closed");
  });
}

module.exports = {
  DoorCollect,
  fetchCurrentDoorState,
};