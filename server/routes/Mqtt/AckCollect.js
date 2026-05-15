// server/routes/Mqtt/AckCollect.js
require("dotenv").config();

const mqtt = require("mqtt");
const path = require("path");
const axios = require("axios");
const fs = require("fs");
const Minio = require("minio");
const mongoose = require("mongoose");
const { v4: uuidv4 } = require("uuid");
const { EventSource } = require("eventsource");
const { getClient } = require("./MqttClient");
const config = require("../../config/key");
const {
  DeadboltStatusAPI,
  LoadcellStatusAPI,
  CameraStatusAPI,
} = require("./HealthMqtt");
const { callApiToControlDeadbolt } = require("./DeadboltApiService");
const { ProductUpload } = require("../../model/ProductUpload");

const { syncAnnotationLabels } = require("../Services/AnnotationLabelSyncService");
const aiNotifyService = require("../Services/AiTrainingNotifyService");

const SUB_TOPIC = `chai/device/${config.deviceIdx}/cmd/collect`;
const PUB_TOPIC = `chai/device/${config.deviceIdx}/ack/collect`;

let client = null;
let chain = Promise.resolve();
let mongoConnectPromise = null;

const collectSessions = new Map();

const minioClient = new Minio.Client({
  endPoint: config.minioURL,
  port: 9000,
  useSSL: false,
  accessKey: config.minioAccessKey,
  secretKey: config.minioSecretKey,
});

async function ensureMongoConnected() {
  if (mongoose.connection.readyState === 1) return;

  if (!mongoConnectPromise) {
    mongoConnectPromise = mongoose.connect(config.mongoURI);
  }

  await mongoConnectPromise;
}

function safe(s) {
  return String(s || "").replace(/[^a-zA-Z0-9._-]/g, "_");
}

function makeTimestampFolderName(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
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

function makeSessionKey(productIdx) {
  return String(productIdx);
}

function publishAck(payload) {
  if (!client || !client.connected) {
    console.error("[AckCollect] MQTT client is not connected. Cannot publish ACK.");
    return;
  }

  client.publish(SUB_TOPIC, JSON.stringify(payload), (err) => {
    if (err) {
      console.error("[AckCollect] ACK publish failed:", err);
    }
  });
}

function makeAckPayload({
  collectState,
  productIdx,
  productEngName,
  categoryIdx,
  isNew,
  resultCd = "S",
  resultMsg = "success",
  health = {},
  extraData = {},
}) {
  return {
    HEADER: {
      IF_ID: "IF_06",
      IF_SYSID: uuidv4(),
      IF_HOST: "EDGEPC01",
      IF_DATE: makeIFDate(),
    },
    DATA: {
      device_idx: config.deviceIdx,
      division_idx: config.divisionIdx,
      product_idx: productIdx,
      collect_state: collectState,
      product_eng_name: productEngName,
      category_idx: categoryIdx,
      is_new: isNew,
      camera_status: health.CameraStatus === "09" ? "1" : "0",
      deadbolt_status: health.DeadboltHealth === "19" ? "1" : "0",
      loadcell_status: health.LoadcellHealth === "29" ? "1" : "0",
      result_cd: resultCd,
      result_msg: resultMsg,
      ...extraData,
    },
  };
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
      } catch {
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

async function cameraStartSampling(savePath, cameraIndices = [0, 2]) {
  const url = `${config.cameraApi}/sampling/start`;

  const body = {
    save_path: savePath,
    cameras: cameraIndices,
  };

  console.log(`[Sampling] Starting... Path: ${savePath}`);

  const response = await axios.post(url, body);

  if (response.status === 200 && response.data?.status === "recording started") {
    console.log("[Sampling] Successfully started");
    return response.data;
  }

  throw new Error(`[Sampling] Start unexpected response: ${JSON.stringify(response.data)}`);
}

async function cameraStopSampling() {
  const url = `${config.cameraApi}/sampling/stop`;

  console.log("[Sampling] Stopping...");

  const response = await axios.post(url);

  if (response.status === 200 && response.data?.status === "recording stopped") {
    console.log("[Sampling] Successfully stopped");
    return response.data;
  }

  throw new Error(`[Sampling] Stop unexpected response: ${JSON.stringify(response.data)}`);
}

async function startLoadcellRecording() {
  const response = await axios.post(`${config.ioboardApi}/start`);

  if (response.status === 200) {
    console.log("[Loadcell] Recording started");
    return response.data;
  }

  throw new Error(`[Loadcell] Start failed: ${JSON.stringify(response.data)}`);
}

async function stopLoadcellRecording() {
  const response = await axios.post(`${config.ioboardApi}/stop`);

  if (response.status === 200) {
    console.log("[Loadcell] Recording stopped");
    return response.data;
  }

  throw new Error(`[Loadcell] Stop failed: ${JSON.stringify(response.data)}`);
}

function getAllFiles(dirPath, arrayOfFiles = []) {
  if (!fs.existsSync(dirPath)) return arrayOfFiles;

  const files = fs.readdirSync(dirPath);

  for (const file of files) {
    const fullPath = path.join(dirPath, file);

    if (fs.statSync(fullPath).isDirectory()) {
      getAllFiles(fullPath, arrayOfFiles);
    } else {
      arrayOfFiles.push(fullPath);
    }
  }

  return arrayOfFiles;
}

function removeEmptyDirs(dir) {
  if (!fs.existsSync(dir)) return;

  const entries = fs.readdirSync(dir);

  for (const entry of entries) {
    const fullPath = path.join(dir, entry);

    if (fs.existsSync(fullPath) && fs.statSync(fullPath).isDirectory()) {
      removeEmptyDirs(fullPath);
    }
  }

  if (fs.existsSync(dir) && fs.readdirSync(dir).length === 0) {
    fs.rmdirSync(dir);
  }
}

function putMinioObject(bucket, objectKey, filePath) {
  return new Promise((resolve, reject) => {
    minioClient.fPutObject(bucket, objectKey, filePath, {}, (err, etag) => {
      if (err) return reject(err);
      resolve(etag);
    });
  });
}

async function uploadFolderToMinio({
  localPath,
  productIdx,
  productEngName,
  timestamp,
  deleteAfterUpload = true,
}) {
  const BUCKET = config.minioBucket;

  if (!localPath || !fs.existsSync(localPath)) {
    return {
      success: false,
      message: `Local folder not found: ${localPath}`,
      filelength: 0,
      objects: [],
    };
  }

  const foldername = `${safe(productIdx)}_${safe(productEngName)}_${safe(timestamp)}`;
  const basePrefix = `productImg/${foldername}`;
  const folderpath = `s3://${BUCKET}/${basePrefix}/`;

  const filesToUpload = getAllFiles(localPath);

  if (!filesToUpload.length) {
    return {
      success: false,
      message: `No files found in folder: ${localPath}`,
      foldername,
      folderpath,
      filelength: 0,
      objects: [],
    };
  }

  const uploaded = [];

  for (const filePath of filesToUpload) {
    const relativePath = path.relative(localPath, filePath).replace(/\\/g, "/");
    const objectKey = `${basePrefix}/${relativePath}`;

    await putMinioObject(BUCKET, objectKey, filePath);

    uploaded.push({
      key: objectKey,
      localPath: filePath,
    });

    if (deleteAfterUpload) {
      try {
        fs.unlinkSync(filePath);
      } catch (err) {
        console.warn(`[MinIO] local file delete failed: ${filePath}`, err.message);
      }
    }
  }

  if (deleteAfterUpload) {
    removeEmptyDirs(localPath);
  }

  return {
    success: true,
    bucket: BUCKET,
    foldername,
    folderpath,
    filelength: uploaded.length,
    objects: uploaded,
  };
}

async function getNextTrainProductIdx() {
  const last = await ProductUpload.findOne({}, { trainProductIdx: 1 })
    .sort({ trainProductIdx: -1 })
    .lean();

  return Number(last?.trainProductIdx ?? 0) + 1;
}

async function syncProductMetadata({
  productIdx,
  productEngName,
  productName,
  categoryIdx,
  isNew,
  foldername,
  folderpath,
  filelength,
}) {
  await ensureMongoConnected();

  const existing = await ProductUpload.findOne(
    { productIdx },
    { trainProductIdx: 1 }
  ).lean();

  const now = new Date();

  const setOnInsert = {};

  if (!existing) {
    setOnInsert.trainProductIdx = await getNextTrainProductIdx();
    setOnInsert.createDate = now;
    setOnInsert.eventPromotion = [];
  }

  await ProductUpload.updateOne(
    { productIdx },
    {
      $set: {
        productIdx,
        productName: productName ?? productEngName,
        productEngName,
        categoryIdx: categoryIdx ?? "null",
        isNew,
        trainingStatus: "2",
        foldername,
        folderpath,
        filelength: Number(filelength || 0),
        updateDate: now,
      },
      ...(Object.keys(setOnInsert).length ? { $setOnInsert: setOnInsert } : {}),
    },
    { upsert: true }
  );

  const updated = await ProductUpload.findOne({ productIdx }).lean();

  console.log(`[MongoDB] Product metadata synced: ${productIdx}`);

  return updated;
}

async function notifyAiTrainingStore(product) {
  if (typeof aiNotifyService.notifyTrainingStore === "function") {
    return aiNotifyService.notifyTrainingStore({
      productIdx: product.productIdx,
      productEngName: product.productEngName,
      trainingStatus: product.trainingStatus || "2",
    });
  }

  if (typeof aiNotifyService.notifyTrainingStoreMany === "function") {
    const result = await aiNotifyService.notifyTrainingStoreMany([
      {
        productIdx: product.productIdx,
        productEngName: product.productEngName,
        trainingStatus: product.trainingStatus || "2",
      },
    ]);

    return result?.[0] ?? result;
  }

  throw new Error(
    "AiTrainingNotifyService must export notifyTrainingStore or notifyTrainingStoreMany"
  );
}

// async function handleStartCollect(reqData) {
//   const {
//     device_idx,
//     division_idx,
//     product_idx,
//     collect_state,
//     product_eng_name,
//     product_name,
//     category_idx,
//     is_new,
//     has_loadcell,
//   } = reqData;

//   if (String(config.deviceIdx) !== String(device_idx)) return;
//   if (String(config.divisionIdx) !== String(division_idx)) return;

//   const healthBefore = await ProductCollectionHealth();

//   const currentDoorState = healthBefore.CurrentDoorState;

//   if (currentDoorState === "CLOSE") {
//     await callApiToControlDeadbolt("OPEN");
//   }

//   const timestamp = makeTimestampFolderName();
//   const productFolder = path.join(
//     process.cwd(),
//     "productImg",
//     `${safe(product_idx)}_${safe(product_eng_name)}_${timestamp}`
//   );

//   const sessionKey = makeSessionKey(product_idx);

//   collectSessions.set(sessionKey, {
//     timestamp,
//     productFolder,
//     productIdx: product_idx,
//     productEngName: product_eng_name,
//     productName: product_name,
//     categoryIdx: category_idx,
//     isNew: is_new,
//     hasLoadcell: has_loadcell,
//     startedAt: new Date(),
//   });

//   await cameraStartSampling(productFolder, [0, 2]);

//   const useLoadcell =
//     has_loadcell === true ||
//     has_loadcell === "1" ||
//     has_loadcell === 1 ||
//     has_loadcell === "Y";

//   if (useLoadcell) {
//     await startLoadcellRecording();
//   }

//   const health = await ProductCollectionHealth();

//   publishAck(
//     makeAckPayload({
//       collectState: collect_state,
//       productIdx: product_idx,
//       productEngName: product_eng_name,
//       categoryIdx: category_idx,
//       isNew: is_new,
//       resultCd: health.isSuccess ? "S" : "F",
//       resultMsg: health.resultMsg,
//       health,
//       extraData: {
//         collection_timestamp: timestamp,
//         local_path: productFolder,
//       },
//     })
//   );
// }

async function handleStartCollect(reqData) {
  const {
    product_idx,
    collect_state,
    product_eng_name,
    product_name,
    category_idx,
    is_new,
    has_loadcell,
  } = reqData;

  console.log("[AckCollect] START collect:", product_idx);

  const healthBefore = await ProductCollectionHealth();

  if (healthBefore.CurrentDoorState === "CLOSE") {
    await callApiToControlDeadbolt("OPEN");
  }

  const timestamp = makeTimestampFolderName();

  const productFolder = path.join(
    process.cwd(),
    "productImg",
    `${safe(product_idx)}_${safe(product_eng_name)}_${timestamp}`
  );

  collectSessions.set(String(product_idx), {
    timestamp,
    productFolder,
    productIdx: product_idx,
    productEngName: product_eng_name,
    productName: product_name,
    categoryIdx: category_idx,
    isNew: is_new,
    hasLoadcell: has_loadcell,
  });

  await cameraStartSampling(productFolder, [0, 2]);

  const useLoadcell =
    has_loadcell === true ||
    has_loadcell === "1" ||
    has_loadcell === 1 ||
    has_loadcell === "Y";

  if (useLoadcell) {
    await startLoadcellRecording();
  }

  const health = await ProductCollectionHealth();

  publishAck(
    makeAckPayload({
      collectState: collect_state,
      productIdx: product_idx,
      productEngName: product_eng_name,
      categoryIdx: category_idx,
      isNew: is_new,
      resultCd: health.isSuccess ? "S" : "F",
      resultMsg: health.resultMsg,
      health,
      extraData: {
        collection_timestamp: timestamp,
        local_path: productFolder,
      },
    })
  );
}

async function waitUntilDoorClosed({ timeoutMs = 60000, intervalMs = 500 } = {}) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const state = await fetchCurrentDoorState();

    if (state === "CLOSE") return true;

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  return false;
}

// async function handleEndCollect(reqData) {
//   const {
//     device_idx,
//     division_idx,
//     product_idx,
//     collect_state,
//     product_eng_name,
//     product_name,
//     category_idx,
//     is_new,
//     has_loadcell,
//   } = reqData;

//   if (String(config.deviceIdx) !== String(device_idx)) return;
//   if (String(config.divisionIdx) !== String(division_idx)) return;

//   const sessionKey = makeSessionKey(product_idx);
//   const session = collectSessions.get(sessionKey);

//   if (!session) {
//     throw new Error(`No active collect session found for product_idx=${product_idx}`);
//   }

//   const closed = await waitUntilDoorClosed();

//   if (!closed) {
//     throw new Error("Door close timeout. Product collection cannot be finalized.");
//   }

//   await cameraStopSampling();

//   const useLoadcell =
//     session.hasLoadcell === true ||
//     session.hasLoadcell === "1" ||
//     session.hasLoadcell === 1 ||
//     session.hasLoadcell === "Y" ||
//     has_loadcell === true ||
//     has_loadcell === "1" ||
//     has_loadcell === 1 ||
//     has_loadcell === "Y";

//   if (useLoadcell) {
//     await stopLoadcellRecording();
//   }

//   const uploadResult = await uploadFolderToMinio({
//     localPath: session.productFolder,
//     productIdx: product_idx,
//     productEngName: product_eng_name || session.productEngName,
//     timestamp: session.timestamp,
//     deleteAfterUpload: true,
//   });

//   if (!uploadResult.success) {
//     throw new Error(uploadResult.message || "MinIO upload failed");
//   }

//   const productDoc = await syncProductMetadata({
//     productIdx: product_idx,
//     productEngName: product_eng_name || session.productEngName,
//     productName: product_name || session.productName,
//     categoryIdx: category_idx || session.categoryIdx,
//     isNew: is_new ?? session.isNew,
//     foldername: uploadResult.foldername,
//     folderpath: uploadResult.folderpath,
//     filelength: uploadResult.filelength,
//   });

//   const annotationResult = await syncAnnotationLabels({
//     productModel: ProductUpload,
//     deleteMissing: false,
//   });

//   const notifyResult = await notifyAiTrainingStore({
//     productIdx: product_idx,
//     productEngName: product_eng_name || session.productEngName,
//     trainingStatus: "2",
//   });

//   const health = await ProductCollectionHealth();

//   publishAck(
//     makeAckPayload({
//       collectState: collect_state,
//       productIdx: product_idx,
//       productEngName: product_eng_name || session.productEngName,
//       categoryIdx: category_idx || session.categoryIdx,
//       isNew: is_new ?? session.isNew,
//       resultCd: "S",
//       resultMsg: "collection completed",
//       health,
//       extraData: {
//         collection_timestamp: session.timestamp,
//         foldername: uploadResult.foldername,
//         folderpath: uploadResult.folderpath,
//         filelength: uploadResult.filelength,
//         train_product_idx: productDoc?.trainProductIdx,
//         annotation: annotationResult,
//         training_notify: notifyResult,
//       },
//     })
//   );

//   collectSessions.delete(sessionKey);
// }

async function handleEndCollect(reqData) {
  const {
    product_idx,
    collect_state,
    product_eng_name,
    product_name,
    category_idx,
    is_new,
    has_loadcell,
  } = reqData;

  console.log("[AckCollect] END collect:", product_idx);

  const session = collectSessions.get(String(product_idx));

  if (!session) {
    throw new Error(`No active collect session found for product_idx=${product_idx}`);
  }

  const closed = await waitUntilDoorClosed();

  if (!closed) {
    throw new Error("Door close timeout. Product collection cannot be finalized.");
  }

  await cameraStopSampling();

  const useLoadcell =
    session.hasLoadcell === true ||
    session.hasLoadcell === "1" ||
    session.hasLoadcell === 1 ||
    session.hasLoadcell === "Y" ||
    has_loadcell === true ||
    has_loadcell === "1" ||
    has_loadcell === 1 ||
    has_loadcell === "Y";

  if (useLoadcell) {
    await stopLoadcellRecording();
  }

  const uploadResult = await uploadFolderToMinio({
    localPath: session.productFolder,
    productIdx: product_idx,
    productEngName: product_eng_name || session.productEngName,
    timestamp: session.timestamp,
    deleteAfterUpload: true,
  });

  if (!uploadResult.success) {
    throw new Error(uploadResult.message || "MinIO upload failed");
  }

  const productDoc = await syncProductMetadata({
    productIdx: product_idx,
    productEngName: product_eng_name || session.productEngName,
    productName: product_name || session.productName,
    categoryIdx: category_idx || session.categoryIdx,
    isNew: is_new ?? session.isNew,
    foldername: uploadResult.foldername,
    folderpath: uploadResult.folderpath,
    filelength: uploadResult.filelength,
  });

  const health = await ProductCollectionHealth();

  publishAck(
    makeAckPayload({
      collectState: collect_state,
      productIdx: product_idx,
      productEngName: product_eng_name || session.productEngName,
      categoryIdx: category_idx || session.categoryIdx,
      isNew: is_new ?? session.isNew,
      resultCd: "S",
      resultMsg: "collection completed",
      health,
      extraData: {
        collection_timestamp: session.timestamp,
        foldername: uploadResult.foldername,
        folderpath: uploadResult.folderpath,
        filelength: uploadResult.filelength,
        train_product_idx: productDoc?.trainProductIdx,
      },
    })
  );

  collectSessions.delete(String(product_idx));
}

async function handleCollectMessage(message) {
  let reqData = {};

  try {
    const reqPayload = JSON.parse(message.toString());
    reqData = reqPayload.DATA || {};

    const {
      device_idx,
      division_idx,
      product_idx,
      collect_state,
      product_eng_name,
    } = reqData;

    console.log("[AckCollect] Request DATA:", reqData);

    if (String(config.deviceIdx) !== String(device_idx)) {
      console.warn("[AckCollect] device_idx mismatch:", {
        configDeviceIdx: config.deviceIdx,
        requestDeviceIdx: device_idx,
      });
      return;
    }

    if (String(config.divisionIdx) !== String(division_idx)) {
      console.warn("[AckCollect] division_idx mismatch:", {
        configDivisionIdx: config.divisionIdx,
        requestDivisionIdx: division_idx,
      });
      return;
    }

    if (collect_state === "START") {
      await handleStartCollect(reqData);
      return;
    }

    if (collect_state === "END") {
      await handleEndCollect(reqData);
      return;
    }

    throw new Error(`Unsupported collect_state: ${collect_state}`);
  } catch (error) {
    console.error("[AckCollect] Processing Error:", error.message);

    const health = await ProductCollectionHealth().catch(() => ({}));

    publishAck(
      makeAckPayload({
        collectState: reqData.collect_state || "UNKNOWN",
        productIdx: reqData.product_idx,
        productEngName: reqData.product_eng_name,
        categoryIdx: reqData.category_idx,
        isNew: reqData.is_new,
        resultCd: "F",
        resultMsg: error.message,
        health,
      })
    );
  }
}

// async function handleCollectMessage(message) {
//   let reqPayload = {};
//   let reqData = {};

//   try {
//     reqPayload = JSON.parse(message.toString());
//     reqData = reqPayload.DATA || {};

//     const collectState = reqData.collect_state;

//     console.log(`[AckCollect] Request Received: ${collectState}`);

//     if (collectState === "START") {
//       await handleStartCollect(reqData);
//       return;
//     }

//     if (collectState === "END") {
//       await handleEndCollect(reqData);
//       return;
//     }

//     throw new Error(`Unsupported collect_state: ${collectState}`);
//   } catch (error) {
//     console.error("[AckCollect] Processing Error:", error);

//     const health = await ProductCollectionHealth().catch(() => ({}));

//     publishAck(
//       makeAckPayload({
//         collectState: reqData.collect_state || "UNKNOWN",
//         productIdx: reqData.product_idx,
//         productEngName: reqData.product_eng_name,
//         categoryIdx: reqData.category_idx,
//         isNew: reqData.is_new,
//         resultCd: "F",
//         resultMsg: error?.message || String(error),
//         health,
//       })
//     );
//   }
// }

// async function AckCollect() {
//   if (client) return;

//   client = mqtt.connect(BROKER_URL);

//   client.on("connect", () => {
//     client.subscribe(CMD_TOPIC, (err) => {
//       if (err) {
//         console.error("[AckCollect] MQTT subscribe failed:", err);

//         publishAck(
//           makeAckPayload({
//             collectState: "SUBSCRIBE",
//             resultCd: "F",
//             resultMsg: `MQTT subscribe failed: ${err.message}`,
//           })
//         );

//         return;
//       }

//       console.log(`[AckCollect] subscribed: ${CMD_TOPIC}`);
//     });
//   });

//   client.on("message", (topic, message) => {
//     if (topic !== CMD_TOPIC) return;

//     chain = chain
//       .then(() => handleCollectMessage(message))
//       .catch((err) => {
//         console.error("[AckCollect] chain error:", err);
//       });
//   });

//   client.on("error", (err) => {
//     console.error("[AckCollect] MQTT client error:", err);
//   });

//   client.on("close", () => {
//     console.warn("[AckCollect] MQTT client closed");
//   });
// }

async function AckCollect() {

  const client = getClient();
  // console.log("[AckCollect] BROKER_URL:", BROKER_URL);
  // console.log("[AckCollect] CMD_TOPIC:", CMD_TOPIC);
  // console.log("[AckCollect] ACK_TOPIC:", ACK_TOPIC);

  // client.on("connect", () => {
  //   client.subscribe(SUB_TOPIC);
  // });
  client.subscribe(SUB_TOPIC, { qos: 1 }, (err, granted) => {
    if (err) {
      console.error("[ACK-COLLECT] Subscribe Error:", err.message);
      return;
    }

    // console.log("[ACK-COLLECT] Subscribe granted:", granted);
    console.log(`[ACK-COLLECT] Subscribed: ${granted}`);
  });

  client.on("message", (topic, message) => {
    console.log("[AckCollect] message received topic:", topic);

    if (topic !== CMD_TOPIC) return;

    chain = chain
      .then(() => handleCollectMessage(message))
      .catch((err) => {
        console.error("[AckCollect] chain error:", err);
      });
  });

  client.on("error", (err) => {
    console.error("[AckCollect] MQTT error:", err.message);
  });

  client.on("close", () => {
    console.warn("[AckCollect] MQTT closed");
  });
}

module.exports = {
  AckCollect,
  fetchCurrentDoorState,
  ProductCollectionHealth,
};

// const mqtt = require('mqtt');
// const path = require('path');
// const config = require("../../config/key");
// const { DeadboltStatusAPI, LoadcellStatusAPI, CameraStatusAPI } = require('../Mqtt/HealthMqtt');
// const { callApiToControlDeadbolt } = require('../Mqtt/DeadboltApiService');
// const { ProductUpload } = require("../../model/ProductUpload");

// const { v4: uuidv4 } = require("uuid");
// const axios = require('axios');
// const fs = require("fs");
// const Minio = require("minio");
// const glob = require("glob"); // 패턴 매칭으로 파일을 찾기 위해 권장 (npm install glob)
// const { tr } = require('zod/locales');

// const minioClient = new Minio.Client({
//   endPoint: config.minioURL,
//   port: 9000,
//   useSSL: false,
//   accessKey: config.minioAccessKey,
//   secretKey: config.minioSecretKey,
// });

// const BROKER_URL = `${config.mqttURL}`;
// const DEVICE_IDX = `${config.deviceIdx}`;

// const CMD_TOPIC = `chai/device/${DEVICE_IDX}/cmd/collect`;
// const ACK_TOPIC = `chai/device/${DEVICE_IDX}/ack/collect`;

// let client = null;
// let chain = Promise.resolve();  // IF06 순차처리용 Promise 체인
// let isDoorClosed = false;

// function makeTimestampFolderName(d = new Date()) {
//   const yyyy = d.getFullYear();
//   const mm = String(d.getMonth() + 1).padStart(2, "0");
//   const dd = String(d.getDate()).padStart(2, "0");
//   const HH = String(d.getHours()).padStart(2, "0");
//   const MM = String(d.getMinutes()).padStart(2, "0");
//   const SS = String(d.getSeconds()).padStart(2, "0");
//   return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
// }

// function makeTimestamp(d = new Date()) {
//   const yyyy = d.getFullYear();
//   const mm = String(d.getMonth() + 1).padStart(2, "0");
//   const dd = String(d.getDate()).padStart(2, "0");
//   const HH = String(d.getHours()).padStart(2, "0");
//   const MM = String(d.getMinutes()).padStart(2, "0");
//   const SS = String(d.getSeconds()).padStart(2, "0");
//   return `${yyyy}${mm}${dd}${HH}${MM}${SS}`;
// }

// function fetchCurrentDoorState() {
//     return new Promise((resolve, reject) => {
//         const url = `${config.ioboardApi}/sse?streams=doors`;
//         const evtSource = new EventSource(url);
//         const timeout = setTimeout(() => {
//             evtSource.close();
//             console.warn("[DoorCheck] Timeout");
//             resolve("UNKNOWN");
//         }, 3000);

//         evtSource.addEventListener('door.update', (event) => {
//             if (!event.data) return;
//             try {
//                 const data = JSON.parse(event.data);
//                 const rawState = data.deadbolt ? data.deadbolt.toUpperCase() : "";
//                 const closedStates = ["LOCK", "LOCKED", "CLOSE", "CLOSED"];
//                 const finalState = closedStates.includes(rawState) ? "CLOSE" : "OPEN";

//                 clearTimeout(timeout);
//                 evtSource.close();
//                 resolve(finalState);
//             } catch (err) {
//                 clearTimeout(timeout);
//                 evtSource.close();
//                 resolve("UNKNOWN");
//             }
//         });
//         evtSource.onerror = (err) => {
//             clearTimeout(timeout);
//             evtSource.close();
//             resolve("UNKNOWN");
//         };
//     });
// }

// async function ProductCollectionHealth() {
//     const CameraStatus = await CameraStatusAPI(); // 예: '09'는 정상이라고 가정
//     const DeadboltHealth = await DeadboltStatusAPI();
//     const LoadcellHealth = await LoadcellStatusAPI();
//     const CurrentDoorState = await fetchCurrentDoorState();
    
//     const isHealthOk = (CameraStatus === '09' && DeadboltHealth === '19' && LoadcellHealth === '29');
//     isSuccess = isHealthOk;
//     resultMsg = (isHealthOk) ? "status access" : "status error";

//     return {CameraStatus, DeadboltHealth, LoadcellHealth, CurrentDoorState, isSuccess, resultMsg}
// }

// // function ensureClientOnce() {
// //   if (client) return;

// //   client = mqtt.connect(BROKER_URL);
// //   client.on('connect', () => client.subscribe(CMD_TOPIC));

// //   client.on('message', (topic, message) => {
// //     if (topic !== CMD_TOPIC) return;

// //     chain = chain
// //       .then(() => handleCollectMessage(message))
// //       .catch(err => console.error('[Collect] 처리 실패:', err));
// //   });
// // }

// async function AckCollect() {
//   // ensureClientOnce();
//   if (client) return;

//   client = mqtt.connect(BROKER_URL);
//   client.on('connect', () => client.subscribe(CMD_TOPIC));

//   client.on('message', (topic, message) => {
//     if (topic !== CMD_TOPIC) return;

//     chain = chain
//       .then(() => handleCollectMessage(message))
//       .catch(err => console.error('[Collect] 처리 실패:', err));
//   });
// }

// async function handleCollectMessage(message) {
//   const ReqPayload = JSON.parse(message.toString());
//   const ReqData = ReqPayload.DATA;

//   const {
//     device_idx, division_idx, product_idx, 
//     collect_state, product_eng_name, category_idx,is_new,
//   } = ReqData;

//   if ((config.deviceIdx != device_idx) || (config.divisionIdx != division_idx)) return;

//   const timestamp = makeTimestampFolderName();
//   const productFolder = path.join(process.cwd(), "productImg", `${product_idx}_${product_eng_name}_${timestamp}`); // 카메라 저장 경로 설정 --> product_idx 말고 mongodb의 trainProductIdx로 변경

//   if (collect_state == "START") { // 픽앤탁이 EdgePC로 "수집 시작해~" 라는 내용을 PUB 하면

//     const CurrentDoorState = await fetchCurrentDoorState();
//     if (CurrentDoorState === "CLOSE") {
//         // IF04에서 한번 열었지만 9초가 지나서 다시 닫힐 수 있으니
//         // 현재 문이 닫혀있는 상태이면
//         const openResult = await callApiToControlDeadbolt("OPEN"); // 열기
//     }

//     // 수집 제어 (시작)
//     await CamerastartSampling(productFolder, [0, 2]); // 카메라 키고
//     await startLoadcellRecording(); // 카메라 끄고

//     const health = await ProductCollectionHealth(); // EdgecPC가 픽앤탁으로 "나 수집 시작할게~" 하는 내용을 PUB
//     const ackPayload = {
//         HEADER: {
//         IF_ID: "IF_06",
//         IF_SYSID: uuidv4(),
//         IF_HOST: "EDGEPC01",
//         IF_DATE: makeTimestamp(),
//         },
//         DATA: {
//         device_idx: config.deviceIdx,
//         division_idx: config.divisionIdx,
//         product_idx: product_idx,
//         collect_state: collect_state,
//         product_eng_name: product_eng_name,
//         category_idx: category_idx,
//         is_new: is_new,
//         camera_status: (health.CameraStatus === '09') ? "1" : "0",
//         deadbolt_status: (health.DeadboltHealth === '19') ? "1" : "0",
//         loadcell_status: (health.LoadcellHealth === '29') ? "1" : "0",
//         result_cd: health.isSuccess ? "S" : "F",
//         result_msg: health.resultMsg,
//         }
//     };

//     client.publish(ACK_TOPIC, JSON.stringify(ackPayload)); 
//     // 문 열은 후에, "나 이제 수집 시작할게"라는 내용을 EdgePC가 픽앤탁으로 PUB
//     }

//     else if (collect_state == "END"){ // 픽앤탁이 EdgePC로 "수집 끝~" 라는 내용을 PUB 하면
//         while (!isDoorClosed) {
//             await new Promise(r => setTimeout(r, 500)); // 0.5초 간격으로 
//             const checkState = await fetchCurrentDoorState(); // 현재 진짜 문이 닫혀있는 상황인지 보고
//             if (checkState === "CLOSE") isDoorClosed = true; // 진짜 문이 닫혀있는 상황이면 무한 루프를 빠져나와
//         }

//         await CamerastopSampling(); // 카메라 끄고
//         await stopLoadcellRecording(); // 로드셀 끄고
//         // const openResult = await callApiToControlDeadbolt("CLOSE"); // 데드볼트도 제어 (닫기)


//         // 3. MinIO 업로드 & MongoDB 업로드 시작
//         if (productFolder && fs.existsSync(productFolder)) {
//         console.log(`[MinIO] Upload starting: ${productFolder}`);
//         try { // MinIO로 상위 폴더의 경로를 입력받아 이미지 데이터 업로드
//             await uploadFolderToMinio(productFolder, product_idx);
//         } catch (err) {
//             console.error(`[MinIO] Upload failed:`, err);
//         }
//         try{
//             await syncProductMetadata({ 
//                 // [질문] 몽고디비로 메타데이터를 전달하는데
//                 // 현재는 다음과 같은 4개의 데이터를 전달하는데
//                 // 추가적으로 어떠한 데이터를 전송하면 되는지?
//                 // 그리고 엑셀 파일에는 training_status가 아니라 status라고 적혀있는데
//                 // status로 받아오면 되는건지?
//                 // 그리고 픽앤탁 서버에서 status 값을 보내주지 않아서 현재는 EdgePC도 보내지 않도록 하고 있는데
//                 // 그래도 괜찮은지?
//                 product_idx,
//                 product_eng_name,
//                 category_idx,
//                 is_new,
//             });
//         } catch (err) {
//             console.error(`[MongoDB] Sync failed:`, err);
//         }
//         }
//         const health = await ProductCollectionHealth(); // EdgecPC가 픽앤탁으로 "나 수집 마칠게~" 하는 내용을 PUB
//         const ackPayload = {
//             HEADER: {
//             IF_ID: "IF_06",
//             IF_SYSID: uuidv4(),
//             IF_HOST: "EDGEPC01",
//             IF_DATE: makeTimestamp(),
//             },
//             DATA: {
//             device_idx: config.deviceIdx,
//             division_idx: config.divisionIdx,
//             product_idx: product_idx,
//             collect_state: collect_state,
//             product_eng_name: product_eng_name,
//             category_idx: category_idx,
//             is_new: is_new,
//             camera_status: (health.CameraStatus === '09') ? "1" : "0",
//             deadbolt_status: (health.DeadboltHealth === '19') ? "1" : "0",
//             loadcell_status: (health.LoadcellHealth === '29') ? "1" : "0",
//             result_cd: health.isSuccess ? "S" : "F",
//             result_msg: health.resultMsg,
//             }
//         };

//         client.publish(ACK_TOPIC, JSON.stringify(ackPayload));
//     }
// }

// async function CamerastartSampling(savePath, cameraIndices) {
//     try {
//         const url = `${config.cameraApi}/sampling/start`;
//         const body = {
//             save_path: savePath,
//             cameras: cameraIndices
//         };

//         console.log(`[Sampling] Starting... Path: ${savePath}`);
//         const response = await axios.post(url, body);

//         if (response.status === 200 && response.data.status === "recording started") {
//             console.log("[Sampling] Successfully started");
//             return response.data;
//         } else {
//             throw new Error(`Unexpected response: ${JSON.stringify(response.data)}`);
//         }
//     } catch (error) {
//         console.error("[Sampling] Start failed:", error.response?.data || error.message);
//         throw error;
//     }
// }

// async function startLoadcellRecording() {
//     try {
//         const response = await axios.post(`${config.ioboardApi}/start`);
//         if (response.status === 200) {
//             console.log("[신규 상품 등록] 로드셀 기록이 시작되었습니다.");
//         }
//     } catch (error) {
//         console.error("기록 시작 실패:", error.message);
//     }
// }

// async function CamerastopSampling() {
//     try {
//         const url = `${config.cameraApi}/sampling/stop`;
        
//         console.log("[Sampling] Stopping...");
//         const response = await axios.post(url);


//         if (response.status === 200 && response.data.status === "recording stopped") {
//             console.log("[Sampling] Successfully stopped");
//             return response.data;
//         } else {
//             throw new Error(`Unexpected response: ${JSON.stringify(response.data)}`);
//         }
//     } catch (error) {
//         console.error("[Sampling] Stop failed:", error.response?.data || error.message);
//         throw error;
//     }
// }

// async function stopLoadcellRecording() {
//     try {
//         const response = await axios.post(`${config.ioboardApi}/stop`);
//         if (response.status === 200) {
//             console.log("[신규 상품 등록] 로드셀 기록이 중지되었습니다.");
//         }
//     } catch (error) {
//         console.error("기록 중지 실패:", error.message);
//     }
// }

// async function uploadFolderToMinio(localPath, productIdx) {
//   const BUCKET = config.minioBucket;
//   const folderName = path.basename(localPath);
//   const basePrefix = `productImg/${safe(productIdx)}_${folderName.split('_').pop()}`;

//   // 1. 모든 파일 목록 가져오기
//   const getAllFiles = (dirPath, arrayOfFiles = []) => {
//     const files = fs.readdirSync(dirPath);
//     files.forEach(file => {
//       const fullPath = path.join(dirPath, file);
//       if (fs.statSync(fullPath).isDirectory()) {
//         arrayOfFiles = getAllFiles(fullPath, arrayOfFiles);
//       } else {
//         arrayOfFiles.push(fullPath);
//       }
//     });
//     return arrayOfFiles;
//   };

//   const filesToUpload = getAllFiles(localPath);

//   // 2. 순차 업로드
//   for (const filePath of filesToUpload) {
//     const relativePath = path.relative(localPath, filePath);
//     const objectKey = `${basePrefix}/${relativePath.replace(/\\/g, '/')}`;

//     await new Promise((resolve, reject) => {
//       minioClient.fPutObject(BUCKET, objectKey, filePath, {}, (err, etag) => {
//         if (err) return reject(err);
//         resolve(etag);
//       });
//     });

//     fs.unlinkSync(filePath);
//   }

//   const removeEmptyDirs = (dir) => {
//     const files = fs.readdirSync(dir);
//     if (files.length > 0) {
//       files.forEach(file => {
//         const fullPath = path.join(dir, file);
//         if (fs.statSync(fullPath).isDirectory()) removeEmptyDirs(fullPath);
//       });
//     }
//     if (fs.readdirSync(dir).length === 0) fs.rmdirSync(dir);
//   };

//   removeEmptyDirs(localPath);
// }

// async function syncProductMetadata(p) {
//   try {
//     const last = await ProductUpload.findOne({}, { trainProductIdx: 1 })
//       .sort({ trainProductIdx: -1 })
//       .lean();
//     let seq = Number(last?.trainProductIdx ?? 0);

//     const now = new Date();
//     const trainProductIdx = ++seq;

//     await ProductUpload.updateOne(
//       { productIdx: p.product_idx },
//       {
//         $set: {
//           categoryIdx: p.category_idx ?? "null",
//           isNew: p.is_new,
//           trainingStatus: "COLLECTED", // 수집 완료 상태로 기록
//           updateDate: now,
//         },
//         $setOnInsert: {
//           productIdx: p.product_idx,
//           productName: p.product_name, // API에서 받아온 이름이 있다면 할당
//           productEngName: p.product_eng_name,
//           trainProductIdx: trainProductIdx,
//           createDate: now,
//           // MinIO에 올린 경로와 일치하도록 설정
//           folderpath: `/productImg/${p.product_idx}_${p.product_eng_name}_${makeTimestampFolderName(now)}/`,
//           eventPromotion: [],
//         },
//       },
//       { upsert: true }
//     );
//     console.log(`[DB] Product ${p.product_idx} metadata uploaded.`);
//   } catch (error) {
//     console.error("[DB Error] Failed to sync product metadata:", error);
//   }
// }

// module.exports = { AckCollect };

