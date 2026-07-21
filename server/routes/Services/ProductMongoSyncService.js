// ============================================================
// ProductMongoSyncService.js
// 역할: 클라우드 REST API(ModelBrunchCheck: device 목록, ProductList: 상품
//       목록)를 호출해 로컬 MongoDB의 DivisionList/ProductsList/
//       DeviceTypeList 컬렉션을 upsert 동기화하는 서비스.
//       storageType(C/F -> COLD/FROZEN) 분류, trainProductIdx 시퀀스 발급,
//       storageType별 brunchName({divisionIdx}_C|F) 구성, 신규/미학습 상품
//       (isNew=0 & trainingStatus 0|1) 필터링을 담당한다.
// 사용처: 현재 어디에서도 require되지 않음(미사용). 유사 로직의 테스트
//       스크립트가 server/test/mongodbDataUpload.js 등에 존재한다.
// ============================================================
require("dotenv").config();
const config = require("../../config/key");

const { DivisionUpload } = require("../../model/DivisionUpload");
const { DeviceTypeUpload } = require("../../model/DeviceTypeUpload");
const { ProductUpload } = require("../../model/ProductUpload");

const { ModelBrunchCheck } = require("../../routes/RestAPI/ModelBrunchCheck");
const { ProductList } = require("../../routes/RestAPI/ProductList");

// snapshot 폴더명에 쓰는 "YYYYMMDD_HHMMSS" 형식의 timestamp 문자열 생성.
function makeFolderTimestamp(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
}

// API의 storage_type 문자('C'|'F')를 DB 표기('COLD'|'FROZEN')로 변환.
// 이미 변환된 값은 그대로 통과시키고, 그 외에는 "UNKNOWN"을 반환한다.
function mapStorageType(storageTypeChar) {
  if (storageTypeChar === "C") return "COLD";
  if (storageTypeChar === "F") return "FROZEN";
  if (storageTypeChar === "COLD" || storageTypeChar === "FROZEN") return storageTypeChar;
  return "UNKNOWN";
}

// brunchName 접미사 변환: COLD -> "C", FROZEN -> "F", 그 외 -> "U".
function brunchSuffixFromStorageType(storageType) {
  if (storageType === "COLD") return "C";
  if (storageType === "FROZEN") return "F";
  return "U";
}

// 배열에서 key 값이 null/undefined가 아닌 첫 항목의 값을 반환(없으면 null).
function pickFirstNonNull(arr, key) {
  for (const x of arr) {
    if (x?.[key] != null) return x[key];
  }
  return null;
}

// ProductList 응답의 상품 배열 위치가 스펙별로 달라 여러 경로를 순서대로 시도.
function normalizeProductListResponse(resp) {
  return (
    resp?.DATA?.product_list ||
    resp?.body?.products ||
    resp?.products ||
    []
  );
}

// ModelBrunchCheck 응답의 device 배열 위치가 스펙별로 달라 여러 경로를 순서대로 시도.
function normalizeDeviceListResponse(resp) {
  return (
    resp?.DATA?.device_list ||
    resp?.body?.devices ||
    resp?.devices ||
    []
  );
}

// division 단위 메타데이터 전체 동기화의 메인 함수.
// 1) ModelBrunchCheck로 device 목록 조회 -> DivisionList upsert
// 2) ProductList로 상품 조회 -> ProductsList upsert(신규 상품에만 trainProductIdx
//    시퀀스 발급, isNew=0 & trainingStatus 0|1 상품은 newOrPendingProducts로 수집)
// 3) storageType(COLD/FROZEN)별로 DeviceTypeList upsert(brunchName, modelVersion,
//    products 매핑 포함)
// 반환: { success, divisionIdx, deviceIdx, products, newOrPendingProducts }
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

// MinIO 업로드 완료 후 ProductsList 문서에 snapshot 폴더 정보(foldername/
// folderpath/filelength)와 trainingStatus, updateDate를 반영한다.
// productEngName이 있으면 (productIdx, productEngName) 복합 키로 매칭한다.
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
