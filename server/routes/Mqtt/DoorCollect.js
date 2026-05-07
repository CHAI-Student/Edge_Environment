// server/routes/Mqtt/DoorCollect.js
const path = require("path");
const mongoose = require("mongoose");
const { v4: uuidv4 } = require("uuid");

const config = require("../../config/key");
const { callApiToControlDeadbolt } = require("./DeadboltApiService");
const {
  DeadboltStatusAPI,
  LoadcellStatusAPI,
  CameraStatusAPI,
} = require("./HealthMqtt");
const { getClient } = require("./MqttClient");
const { DeviceInfo } = require("../RestAPI/DeviceInfo");
const { ProductUpload } = require("../../model/ProductUpload");

const {
  startProductCapture,
  stopProductCapture,
} = require("../Services/ProductCaptureService");
const {
  uploadProductImages,
  uploadProductVideos,
} = require("../Services/ProductMinioService");
const {
  syncDivisionProductMetadata,
  updateProductUploadFolder,
  makeFolderTimestamp,
} = require("../Services/ProductMongoSyncService");
const { syncAnnotationLabels } = require("../Services/AnnotationLabelSyncService");
const { notifyTrainingStoreMany } = require("../Services/AiTrainingNotifyService");

let mongoConnectPromise = null;
let activeCollectionSession = null;

async function ensureMongoConnected() {
  if (mongoose.connection.readyState === 1) return;
  if (!mongoConnectPromise) {
    mongoConnectPromise = mongoose.connect(config.mongoURI);
  }
  await mongoConnectPromise;
}

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
  ifId,
  reqStorageType,
  reqHasLoadCell,
  doorState,
  resultCd = "S",
  resultMsg = "success",
  extraData = {},
}) {
  return {
    HEADER: {
      IF_ID: ifId,
      IF_SYSID: uuidv4(),
      IF_HOST: "CRKPNTCCHAI",
      IF_DATE: makeIFDate(),
    },
    DATA: {
      division_idx: config.divisionIdx,
      device_idx: config.deviceIdx,
      door_state: doorState,
      storage_type: reqStorageType,
      has_loadcell: reqHasLoadCell,
      result_cd: resultCd,
      result_msg: resultMsg,
      ...extraData,
    },
  };
}

function publishAck(client, topic, payload) {
  client.publish(topic, JSON.stringify(payload));
}

function normalizeDeviceInfoResponse(resp) {
  return resp?.DATA?.device_list || resp?.body?.devices || resp?.devices || resp || [];
}

function ModelVersionUpdate(version) {
  if (!version) return "1.0.0";

  const parts = String(version).split(".");
  const lastIndex = parts.length - 1;
  const lastValue = parseInt(parts[lastIndex], 10);

  if (Number.isNaN(lastValue)) return `${version}.1`;

  parts[lastIndex] = String(lastValue + 1);
  return parts.join(".");
}

async function fetchCurrentDoorState() {
  return new Promise((resolve) => {
    const url = `${config.ioboardApi}/sse?streams=doors`;
    const evtSource = new EventSource(url);

    const timeout = setTimeout(() => {
      evtSource.close();
      console.warn("[DoorCheck] Timeout");
      resolve("UNKNOWN");
    }, 3000);

    evtSource.addEventListener("door.update", (event) => {
      if (!event.data) return;

      try {
        const data = JSON.parse(event.data);
        const rawState = data.deadbolt ? data.deadbolt.toUpperCase() : "";
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

  const isHealthOk =
    CameraStatus === "09" && DeadboltHealth === "19" && LoadcellHealth === "29";

  return {
    CameraStatus,
    DeadboltHealth,
    LoadcellHealth,
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

  const timestamp = makeFolderTimestamp();
  const localRoot = path.join(process.cwd(), "productImg", timestamp);

  activeCollectionSession = {
    timestamp,
    localRoot,
    storageType: reqStorageType,
    hasLoadcell: reqHasLoadCell,
    startedAt: new Date(),
  };
  
  await startProductCapture({
    localRoot,
    timestamp,
    deviceIdx: config.deviceIdx,
    cameras: ["cam_0", "cam_2"],
  });

  const ackPayload = makeAckPayload({
    ifId: "IF_04",
    reqStorageType,
    reqHasLoadCell,
    doorState: await fetchCurrentDoorState(),
    resultCd: health.isSuccess ? "S" : "F",
    resultMsg: health.resultMsg,
    extraData: {
      camera_status: health.CameraStatus === "09" ? "1" : "0",
      deadbolt_status: health.DeadboltHealth === "19" ? "1" : "0",
      loadcell_status: health.LoadcellHealth === "29" ? "1" : "0",
      collection_timestamp: timestamp,
      local_root: localRoot,
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

  await ensureMongoConnected();

  const session =
    activeCollectionSession || {
      timestamp: makeFolderTimestamp(),
      localRoot: path.join(process.cwd(), "productImg", makeFolderTimestamp()),
      storageType: reqStorageType,
      hasLoadcell: reqHasLoadCell,
      startedAt: null,
    };

  await stopProductCapture({
    localRoot: session.localRoot,
    timestamp: session.timestamp,
    deviceIdx: config.deviceIdx,
    cameras: ["cam_0", "cam_2"],
  });

  const syncResult = await syncDivisionProductMetadata({
    divisionIdx: config.divisionIdx,
    deviceIdx: config.deviceIdx,
  });

  const targetProducts = syncResult.newOrPendingProducts.length
    ? syncResult.newOrPendingProducts
    : syncResult.products;

  if (!targetProducts.length) {
    const ackPayload = makeAckPayload({
      ifId: "IF_06",
      reqStorageType,
      reqHasLoadCell,
      doorState: currentDoorState,
      resultCd: "F",
      resultMsg: "업로드/학습 전달 대상 상품이 없습니다.",
      extraData: {
        collection_timestamp: session.timestamp,
        local_root: session.localRoot,
      },
    });

    publishAck(client, ackTopic, ackPayload);
    activeCollectionSession = null;
    return;
  }

  // 현재 수집 세션은 하나의 신규 상품 촬영을 기준으로 처리한다.
  // 여러 신규 상품이 동시에 잡히는 정책이면 여기서 상품별 폴더 분리 정책이 필요하다.
  const targetProduct = targetProducts[0];
  const uploadProductIdx = targetProduct.trainProductIdx || targetProduct.productIdx;

  const imageUploadResult = await uploadProductImages({
    productIdx: uploadProductIdx,
    timestamp: session.timestamp,
    localRoot: session.localRoot,
    cameras: ["cam_0", "cam_2"],
    deleteAfterUpload: false,
  });

  const videoUploadResult = await uploadProductVideos({
    productIdx: uploadProductIdx,
    timestamp: session.timestamp,
    localRoot: session.localRoot,
    cameras: ["cam_0", "cam_2"],
    deleteAfterUpload: true,
  });

  const deviceInfoResp = await DeviceInfo();
  const deviceList = normalizeDeviceInfoResponse(deviceInfoResp);
  const myDevice = deviceList.find((device) => {
    const d = device.device_idx ?? device.deviceIdx;
    return String(d) === String(config.deviceIdx);
  });

  const currentModelVersion = myDevice?.model_version || myDevice?.modelVersion;
  const updateModelVersion = ModelVersionUpdate(currentModelVersion);

  await ProductUpload.updateMany(
    { productIdx: { $in: targetProducts.map((p) => p.productIdx) } },
    {
      $set: {
        trainingStatus: "2",
        modelVersion: updateModelVersion,
        updateDate: new Date(),
      },
    }
  );

  await updateProductUploadFolder({
    productIdx: targetProduct.productIdx,
    productEngName: targetProduct.productEngName,
    foldername: imageUploadResult.foldername,
    folderpath: imageUploadResult.folderpath,
    filelength:
      Number(imageUploadResult.filelength || 0) +
      Number(videoUploadResult.filelength || 0),
    modelVersion: updateModelVersion,
    trainingStatus: "2",
  });

  const annotationResult = await syncAnnotationLabels({
    productModel: ProductUpload,
    deleteMissing: false,
  });

  const notifyProducts = targetProducts.map((p) => ({
    productIdx: p.productIdx,
    productEngName: p.productEngName,
    trainingStatus: "2",
  }));

  const notifyResult = await notifyTrainingStoreMany(notifyProducts);

  const ackPayload = makeAckPayload({
    ifId: "IF_06",
    reqStorageType,
    reqHasLoadCell,
    doorState: currentDoorState,
    resultCd: imageUploadResult.success ? "S" : "F",
    resultMsg: imageUploadResult.success
      ? "collection upload and training notification completed"
      : imageUploadResult.message || "image upload failed",
    extraData: {
      collection_timestamp: session.timestamp,
      foldername: imageUploadResult.foldername,
      folderpath: imageUploadResult.folderpath,
      image_filelength: imageUploadResult.filelength,
      video_filelength: videoUploadResult.filelength,
      model_version: updateModelVersion,
      annotation: annotationResult,
      training_notify: notifyResult.map((x) => ({
        product_idx: x.productIdx,
        product_eng_name: x.productEngName,
        success: x.success,
      })),
    },
  });

  publishAck(client, ackTopic, ackPayload);
  activeCollectionSession = null;
}

async function DoorCollect() {
  const DoorCollect_SUB_TOPIC = `chai/device/${config.deviceIdx}/cmd/door/collect`;
  const DoorCollect_PUB_TOPIC = `chai/device/${config.deviceIdx}/ack/door/collect`;

  const client = getClient();

  client.on("connect", () => {
    client.subscribe(DoorCollect_SUB_TOPIC);
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
        ifId: "IF_06",
        reqStorageType: reqData.storage_type,
        reqHasLoadCell: reqData.has_loadcell,
        doorState: reqData.door_state || "UNKNOWN",
        resultCd: "F",
        resultMsg: error?.message || String(error),
      });

      publishAck(client, DoorCollect_PUB_TOPIC, errorPayload);
    }
  });
}

module.exports = {
  DoorCollect,
  fetchCurrentDoorState,
  ProductCollectionHealth,
};
