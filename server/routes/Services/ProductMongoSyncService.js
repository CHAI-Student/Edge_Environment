require("dotenv").config();
const config = require("../config/key");

const { DivisionUpload } = require("../model/DivisionUpload");
const { DeviceTypeUpload } = require("../model/DeviceTypeUpload");
const { ProductUpload } = require("../model/ProductUpload");

const { ModelBrunchCheck } = require("../routes/RestAPI/ModelBrunchCheck");
const { ProductList } = require("../routes/RestAPI/ProductList");

function makeFolderTimestamp(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
}

function mapStorageType(storageTypeChar) {
  if (storageTypeChar === "C") return "COLD";
  if (storageTypeChar === "F") return "FROZEN";
  if (storageTypeChar === "COLD" || storageTypeChar === "FROZEN") return storageTypeChar;
  return "UNKNOWN";
}

function brunchSuffixFromStorageType(storageType) {
  if (storageType === "COLD") return "C";
  if (storageType === "FROZEN") return "F";
  return "U";
}

function pickFirstNonNull(arr, key) {
  for (const x of arr) {
    if (x?.[key] != null) return x[key];
  }
  return null;
}

function normalizeProductListResponse(resp) {
  return (
    resp?.DATA?.product_list ||
    resp?.body?.products ||
    resp?.products ||
    []
  );
}

function normalizeDeviceListResponse(resp) {
  return (
    resp?.DATA?.device_list ||
    resp?.body?.devices ||
    resp?.devices ||
    []
  );
}

async function syncDivisionProductMetadata({
  divisionIdx = config.divisionIdx,
  deviceIdx = config.deviceIdx,
} = {}) {
  const mb = await ModelBrunchCheck({
    division_idx: divisionIdx,
    device_idx: deviceIdx || null,
    productIdx: null,
  });

  const deviceList = normalizeDeviceListResponse(mb);
  if (!deviceList.length) {
    return {
      success: false,
      divisionIdx,
      deviceIdx,
      message: "No devices found",
      products: [],
      newOrPendingProducts: [],
    };
  }

  const targetDivisionIdx = deviceList[0].division_idx || divisionIdx;
  const allDeviceIdx = deviceList.map((d) => d.device_idx).filter(Boolean);

  await DivisionUpload.updateOne(
    { divisionIdx: targetDivisionIdx },
    {
      $set: {
        divisionIdx: targetDivisionIdx,
        deviceIdx: allDeviceIdx,
      },
    },
    { upsert: true }
  );

  const pl = await ProductList({
    division_idx: targetDivisionIdx,
    device_idx: deviceIdx || null,
  });

  const products = normalizeProductListResponse(pl);

  const last = await ProductUpload.findOne({}, { trainProductIdx: 1 })
    .sort({ trainProductIdx: -1 })
    .lean();

  let seq = Number(last?.trainProductIdx ?? 0);

  const productIdxSetByStorage = {
    COLD: new Set(),
    FROZEN: new Set(),
  };

  const syncedProducts = [];
  const newOrPendingProducts = [];

  for (const p of products) {
    const productIdx = p.product_idx ?? p.productIdx;
    const productEngName = p.product_eng_name ?? p.productEngName;
    const storageType = mapStorageType(p.storage_type ?? p.storageType);

    if (!productIdx || !productEngName || storageType === "UNKNOWN") continue;

    productIdxSetByStorage[storageType].add(productIdx);

    const existing = await ProductUpload.findOne(
      { productIdx, productEngName },
      { _id: 1, trainProductIdx: 1, foldername: 1, folderpath: 1 }
    ).lean();

    const isNewInsert = !existing;
    const trainProductIdx = existing?.trainProductIdx || ++seq;

    const setOnInsert = isNewInsert
      ? {
          productIdx,
          productName: p.product_name ?? p.productName ?? null,
          productEngName,
          trainProductIdx,
          createDate: new Date(),
          eventPromotion: [],
        }
      : {};

    await ProductUpload.updateOne(
      { productIdx, productEngName },
      {
        $set: {
          divisionIdx: targetDivisionIdx,
          categoryIdx: p.category_idx ?? p.categoryIdx ?? "null",
          isNew: p.is_new ?? p.isNew ?? null,
          trainingStatus: String(p.training_status ?? p.trainingStatus ?? "2"),
          productLoadcellWeight:
            p.product_loadcell_weight ?? p.productLoadcellWeight ?? "null",
          storageType,
          updateDate: new Date(),
        },
        ...(Object.keys(setOnInsert).length ? { $setOnInsert: setOnInsert } : {}),
      },
      { upsert: true }
    );

    const synced = {
      productIdx,
      productEngName,
      trainProductIdx,
      storageType,
      isNew: String(p.is_new ?? p.isNew ?? ""),
      trainingStatus: String(p.training_status ?? p.trainingStatus ?? ""),
    };

    syncedProducts.push(synced);

    if (
      synced.isNew === "0" &&
      (synced.trainingStatus === "0" || synced.trainingStatus === "1")
    ) {
      newOrPendingProducts.push(synced);
    }
  }

  const devicesByStorage = {
    COLD: [],
    FROZEN: [],
  };

  for (const d of deviceList) {
    const storageType = mapStorageType(d.storage_type ?? d.storageType);
    if (storageType === "COLD") devicesByStorage.COLD.push(d);
    if (storageType === "FROZEN") devicesByStorage.FROZEN.push(d);
  }

  for (const storageType of ["COLD", "FROZEN"]) {
    const devices = devicesByStorage[storageType];
    if (!devices.length) continue;

    const deviceIdxArr = devices.map((x) => x.device_idx ?? x.deviceIdx).filter(Boolean);
    const brunchName = `${targetDivisionIdx}_${brunchSuffixFromStorageType(storageType)}`;
    const modelVersion = pickFirstNonNull(devices, "model_version") ?? pickFirstNonNull(devices, "modelVersion");

    const productIdxList = Array.from(productIdxSetByStorage[storageType] ?? []);
    const productDocs = productIdxList.length
      ? await ProductUpload.find({ productIdx: { $in: productIdxList } }, { _id: 1 }).lean()
      : [];

    const productMappings = productDocs.map((x) => ({
      product: x._id,
      training_status: "2",
    }));

    await DeviceTypeUpload.updateOne(
      { divisionIdx: targetDivisionIdx, storageType },
      {
        $set: {
          storageType,
          divisionIdx: targetDivisionIdx,
          brunchName,
          deviceIdx: deviceIdxArr,
          modelVersion: modelVersion ?? null,
          products: productMappings,
          trainingStatus: "2",
          trainingDate: new Date(),
          retrainingDate: null,
        },
      },
      { upsert: true }
    );
  }

  return {
    success: true,
    divisionIdx: targetDivisionIdx,
    deviceIdx,
    products: syncedProducts,
    newOrPendingProducts,
  };
}

async function updateProductUploadFolder({
  productIdx,
  productEngName,
  foldername,
  folderpath,
  filelength,
  modelVersion,
  trainingStatus = "2",
} = {}) {
  if (!productIdx) throw new Error("productIdx is required");
  if (!foldername) throw new Error("foldername is required");
  if (!folderpath) throw new Error("folderpath is required");

  const filter = productEngName ? { productIdx, productEngName } : { productIdx };

  const update = {
    foldername,
    folderpath,
    filelength: Number(filelength || 0),
    trainingStatus: String(trainingStatus),
    updateDate: new Date(),
  };

  if (modelVersion) update.modelVersion = modelVersion;

  const result = await ProductUpload.updateOne(filter, { $set: update });
  return {
    matchedCount: result.matchedCount,
    modifiedCount: result.modifiedCount,
  };
}

module.exports = {
  syncDivisionProductMetadata,
  updateProductUploadFolder,
  makeFolderTimestamp,
  mapStorageType,
};
