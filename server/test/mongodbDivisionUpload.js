// ============================================================
// mongodbDivisionUpload.js — 수동 실행용 테스트 스크립트
// 역할: ModelBrunchCheck/ProductList API 결과로 DivisionList 1건 upsert와
//       ProductsList 상품 upsert(trainProductIdx 시퀀스 포함) 후 division의
//       products 매핑을 갱신하고 populate로 확인하는 흐름을 검증한다.
// ============================================================
const config = require("../config/key");
const mongoose = require("mongoose");
require("dotenv").config();

const { DivisionUpload } = require("../model/DivisionUpload");
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

async function main() {
  // 1) 로그인 --> 나중에 삭제 필요, 이미 발급된 config 토큰 활용
  const token = await devAutoLogin();
  if (!token) throw new Error("devAutoLogin failed");

  // 2) Mongo 연결 
  await mongoose.connect(config.mongoURI);
  console.log("[MongoDB] connected");

  // 3) 브런치/디바이스 리스트
  const mb = await ModelBrunchCheck({
    division_idx: config.divisionIdx,
    device_idx: null,
    productIdx: null,
  });

  const deviceList = mb.DATA.device_list ?? [];
  console.log("[ModelBrunchCheck] devices:", deviceList.length);
  console.log('mb.DATA', mb.DATA)
  if (!deviceList.length) {
    console.log("[DivisionUpload] no devices found");
    await mongoose.disconnect();
    console.log("[MongoDB] disconnected");
    return;
  }

  // division 정보 불러오기 -> 장비 여러대이지만 동일한 매장
  const divisionIdx = deviceList[0].division_idx;
  const now = new Date();

  // deviceIdx를 배열로 저장
  const deviceIdxArr = deviceList.map((x) => x.device_idx);

  // Division에 저장할 대표 모델/브런치
  const d0 = deviceList[0];

  // Division 1개 upsert (device loop 밖에서 1번만)
  await DivisionUpload.updateOne(
    { divisionIdx },
    {
      $set: {
        divisionIdx,
        deviceIdx: deviceIdxArr,
        modelVersion: d0.model_version == null ? "v0.0.1" : d0.model_version,
        brunchName: `${divisionIdx}_${d0.storage_type}`,
        trainingStatus: "2",
        trainingDate: now,
        retrainingDate: null,
      },
      $setOnInsert: {
        products: [],
      },
    },
    { upsert: true }
  );

  // 4) trainProductIdx 시퀀스 (신규 상품 insert시에만)
  const last = await ProductUpload.findOne({}, { trainProductIdx: 1 })
    .sort({ trainProductIdx: -1 })
    .lean();
  let seq = Number(last?.trainProductIdx ?? 0);

  // device 2개 상품을 union
  const productIdxSet = new Set();

  const pl = await ProductList({ division_idx: divisionIdx, device_idx: null });

  const products = pl.DATA.product_list ?? [];
  // console.log(`[ProductList] device=${deviceIdx} items=${products.length}`);
  console.log(`[ProductList] division=${divisionIdx} devices=${deviceList.length} items=${products.length}`);
  console.log(products)

  for (const p of products) {
    productIdxSet.add(p.product_idx);

    // ProductUpload 갱신(정책: device용은 trainingStatus=2)
    const updateSetProduct = {
      categoryIdx: p.category_idx ?? "null",
      isNew: p.is_new,
      trainingStatus: "2",
      productLoadcellWeight: p.product_weight ?? "null",
    };

    // 상품이 이미 존재하는지 체크 (trainProductIdx만 조회)
    const existing = await ProductUpload.findOne(
      { productIdx: p.product_idx },
      { _id: 1, trainProductIdx: 1, foldername: 1, folderpath: 1 }
    ).lean();

    // 신규일 때만 seq++ + 폴더 생성 + setOnInsert 구성
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
      { productIdx: p.product_idx },
      {
        $set: updateSetProduct,
        ...(Object.keys(setOnInsert).length ? { $setOnInsert: setOnInsert } : {}),
      },
      { upsert: true }
    );
  }

  // union된 productIdx -> ObjectId
  const productIdxList = Array.from(productIdxSet);
  const productDocs = productIdxList.length
    ? await ProductUpload.find({ productIdx: { $in: productIdxList } }, { _id: 1 }).lean()
    : [];

  const productMappings = productDocs.map((x) => ({
    product: x._id,
    training_status: "2",  // 이미 AI 서버 내 데이터 존재
  }));

  await DivisionUpload.updateOne({ divisionIdx }, { $set: { products: [] } });
  await DivisionUpload.updateOne({ divisionIdx }, { $set: { products: productMappings } });

  // populate로 상품 상세 확인
  const division = await DivisionUpload.findOne({ divisionIdx })
    // .populate("products")
    .populate("products.product")
    .lean();

  console.log("[Division] divisionIdx:", division?.divisionIdx);
  console.log("[Division] deviceIdx:", division?.deviceIdx);
  console.log("[Division] products(populated) count:", division?.products?.length ?? 0);
  console.dir(division?.products, { depth: null });

  await mongoose.disconnect();
  console.log("[MongoDB] disconnected");
}

if (require.main === module) {
  main().catch((e) => {
    console.error("[ERROR]", e);
    process.exit(1);
  });
}

// 상태 업데이트 코드
// await DivisionUpload.updateOne(
//   { divisionIdx, "products.product": productObjectId },
//   {
//     $set: {
//       "products.$.training_status": "3",
//       "products.$.updated_at": new Date(),
//       "products.$.last_error": null,
//     },
//   }
// );