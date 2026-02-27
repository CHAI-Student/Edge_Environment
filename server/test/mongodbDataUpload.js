const config = require("../config/key");
const mongoose = require("mongoose");
require("dotenv").config();

const { DivisionUpload } = require("../model/DivisionUpload");
const { DeviceTypeUpload } = require("../model/DeviceTypeUpload");
const { ProductUpload } = require("../model/ProductUpload");

const { devAutoLogin } = require("../routes/auth");
const { ModelBrunchCheck } = require("../routes/RestAPI/ModelBrunchCheck");
const { ProductList } = require("../routes/RestAPI/ProductList");

function FolderName(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
}

// API storage_type: 'C'|'F' -> DB storageType: 'COLD'|'FROZEN'
function mapStorageType(storageTypeChar) {
  if (storageTypeChar === "C") return "COLD";
  if (storageTypeChar === "F") return "FROZEN";
  return "UNKNOWN";
}

// DeviceTypeList brunchName suffix: COLD->C, FROZEN->F
function brunchSuffixFromStorageType(storageType) {
  if (storageType === "COLD") return "C";
  if (storageType === "FROZEN") return "F";
  return "U";
}

// group 내에서 null 아닌 값 하나 뽑기
function pickFirstNonNull(arr, key) {
  for (const x of arr) {
    if (x?.[key] != null) return x[key];
  }
  return null;
}

async function main() {
  // 1) 로그인 (추후 토큰 고정이면 제거 가능)
  const token = await devAutoLogin();
  if (!token) throw new Error("devAutoLogin failed");

  // 2) Mongo 연결
  await mongoose.connect(config.mongoURI);
  console.log("[MongoDB] connected");

  // 3) 디바이스 리스트 (ModelBrunchCheck)
  const mb = await ModelBrunchCheck({
    division_idx: config.divisionIdx,
    device_idx: null,
    productIdx: null,
  });

  const deviceList = mb?.DATA?.device_list ?? [];
  console.log("[ModelBrunchCheck] devices:", deviceList.length);

  if (!deviceList.length) {
    console.log("[Upload] no devices found");
    await mongoose.disconnect();
    console.log("[MongoDB] disconnected");
    return;
  }

  // division은 deviceList 안에서 동일
  const divisionIdx = deviceList[0].division_idx;
  const now = new Date();

  // 4) DivisionList 업서트 (스키마: divisionIdx, deviceIdx[])
  const allDeviceIdx = deviceList.map((d) => d.device_idx);

  await DivisionUpload.updateOne(
    { divisionIdx },
    {
      $set: {
        divisionIdx,
        deviceIdx: allDeviceIdx,
      },
    },
    { upsert: true }
  );

  // 5) ProductList 로 전체 상품 불러오기 (division 단위)
  const pl = await ProductList({ division_idx: divisionIdx, device_idx: null });
  const products = pl?.DATA?.product_list ?? [];
  console.log(`[ProductList] division=${divisionIdx} items=${products.length}`);

  // 6) trainProductIdx 시퀀스: 신규 insert시에만 증가
  const last = await ProductUpload.findOne({}, { trainProductIdx: 1 })
    .sort({ trainProductIdx: -1 })
    .lean();
  let seq = Number(last?.trainProductIdx ?? 0);

  // DeviceTypeList용: storageType별 product_idx set
  const productIdxSetByStorage = {
    COLD: new Set(),
    FROZEN: new Set(),
  };

  // 7) ProductsList 업서트 (+ storageType 저장)
  for (const p of products) {
    const storageType = mapStorageType(p.storage_type); // 'COLD'|'FROZEN'
    if (storageType === "UNKNOWN") continue;

    productIdxSetByStorage[storageType].add(p.product_idx);

    // 업데이트 정책
    const updateSetProduct = {
      categoryIdx: p.category_idx ?? "null",
      isNew: p.is_new ?? null,
      trainingStatus: "2",
      // 로드셀 기반이면 loadcell_weight 우선
      productLoadcellWeight: p.product_loadcell_weight ?? "null",
      // ✅ ProductsList에도 storageType 저장
      storageType, // "COLD"/"FROZEN"
    };

    // 기존 존재 여부 (trainProductIdx/폴더는 최초 insert 시 생성)
    // ⚠️ 같은 productIdx인데 productEngName이 바뀔 수 있어 (샘플에 존재)
    // 그래서 (productIdx + productEngName) 기준으로 문서를 관리
    const existing = await ProductUpload.findOne(
      { productIdx: p.product_idx, productEngName: p.product_eng_name },
      { _id: 1, trainProductIdx: 1, foldername: 1, folderpath: 1 }
    ).lean();

    let setOnInsert = {};
    if (!existing) {
      const insertNow = new Date();
      const trainProductIdx = ++seq;

      const stamp = FolderName(insertNow);
      const foldername = `${trainProductIdx}_${p.product_eng_name}_${stamp}`;
      const folderpath = `/chaiimage/productImg/${foldername}/`;

      setOnInsert = {
        productIdx: p.product_idx,
        productName: p.product_name,
        productEngName: p.product_eng_name,
        trainProductIdx,
        createDate: insertNow,
        foldername,
        folderpath,
        filelength: null,
        updateDate: null,
        eventPromotion: [],
      };
    }

    await ProductUpload.updateOne(
      { productIdx: p.product_idx, productEngName: p.product_eng_name },
      {
        $set: updateSetProduct,
        ...(Object.keys(setOnInsert).length ? { $setOnInsert: setOnInsert } : {}),
      },
      { upsert: true }
    );
  }

  // 8) DeviceTypeList 업서트 (division 당 최대 2개: COLD/FROZEN)
  // mb.DATA.device_list 기준: storageType별로 deviceIdx[] 구성
  const devicesByStorage = {
    COLD: [],
    FROZEN: [],
  };

  for (const d of deviceList) {
    const storageType = mapStorageType(d.storage_type);
    if (storageType === "COLD") devicesByStorage.COLD.push(d);
    else if (storageType === "FROZEN") devicesByStorage.FROZEN.push(d);
  }

  for (const storageType of ["COLD", "FROZEN"]) {
    const devices = devicesByStorage[storageType];
    if (!devices.length) continue;

    const deviceIdxArr = devices.map((x) => x.device_idx);

    // ✅ brunchName은 무조건 ${divisionIdx}_C / ${divisionIdx}_F
    const brunchName = `${divisionIdx}_${brunchSuffixFromStorageType(storageType)}`;

    // ✅ modelVersion은 없으면 null (fallback 제거)
    const modelVersion = pickFirstNonNull(devices, "model_version"); // 없으면 null

    // storageType별 product_idx -> ProductsList _id 매핑 -> DeviceTypeList products 생성
    const productIdxList = Array.from(productIdxSetByStorage[storageType] ?? []);
    const productDocs = productIdxList.length
      ? await ProductUpload.find(
          { productIdx: { $in: productIdxList } },
          { _id: 1 }
        ).lean()
      : [];

    const productMappings = productDocs.map((x) => ({
      product: x._id,
      training_status: "2",
    }));

    await DeviceTypeUpload.updateOne(
      { divisionIdx, storageType },
      {
        $set: {
          storageType, // "COLD"/"FROZEN"
          divisionIdx,
          brunchName, // ✅ 고정 포맷
          deviceIdx: deviceIdxArr,
          modelVersion: modelVersion ?? null, // ✅ 없으면 null
          products: productMappings,
          trainingStatus: "2",
          trainingDate: now,
          retrainingDate: null,
        },
      },
      { upsert: true }
    );

    console.log(
      `[DeviceTypeUpload] upserted division=${divisionIdx} storageType=${storageType} brunchName=${brunchName} devices=${deviceIdxArr.length} products=${productMappings.length} modelVersion=${modelVersion ?? null}`
    );
  }

  // 9) 결과 확인
  const divisionDoc = await DivisionUpload.findOne({ divisionIdx }).lean();
  console.log("[DivisionList] divisionIdx:", divisionDoc?.divisionIdx);
  console.log("[DivisionList] deviceIdx:", divisionDoc?.deviceIdx);

  const deviceTypeDocs = await DeviceTypeUpload.find({ divisionIdx })
    .populate("products.product")
    .lean();

  console.log("[DeviceTypeList] count:", deviceTypeDocs.length);
  for (const dt of deviceTypeDocs) {
    console.log(
      ` - ${dt.storageType} brunch=${dt.brunchName} devices=${dt.deviceIdx?.length ?? 0} products=${dt.products?.length ?? 0} modelVersion=${dt.modelVersion ?? null}`
    );
  }

  await mongoose.disconnect();
  console.log("[MongoDB] disconnected");
}

if (require.main === module) {
  main().catch((e) => {
    console.error("[ERROR]", e);
    process.exit(1);
  });
}