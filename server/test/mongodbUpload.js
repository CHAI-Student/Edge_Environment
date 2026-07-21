// ============================================================
// mongodbUpload.js — 수동 실행용 테스트 스크립트
// 역할: devAutoLogin 후 ProductList API의 상품 목록을 MongoDB ProductsList에
//       upsert(신규 시 trainProductIdx 발급, snapshot 폴더 placeholder 생성)하는
//       기본 업로드 흐름을 단독 실행으로 검증한다.
// ============================================================
const config = require("../config/key");
const mongoose = require("mongoose");
const { ProductUpload } = require("../model/ProductUpload");
require("dotenv").config();

const { devAutoLogin } = require("../routes/auth");
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
  // 1) 로그인 & 토큰
  const token = await devAutoLogin();
  if (!token) throw new Error("devAutoLogin failed");

  // 2) ProductList 호출
  const data = await ProductList({
    division_idx: config.divisionIdx,
    device_idx: null,
  });
  console.log('data', data)
  const list = data.DATA.product_list ?? [];
  console.log("[ProductList] items:", list.length);
  if (!list.length) return;

  // 3) Mongo 연결
  await mongoose.connect(config.mongoURI);
  console.log("[MongoDB] connected");

  // 4) trainProductIdx 시퀀스 시작값 -> 1부터 순차적 증가
  const last = await ProductUpload.findOne({}, { trainProductIdx: 1 })
    .sort({ trainProductIdx: -1 })
    .lean();
  let seq = Number(last?.trainProductIdx ?? 0);

  // 5) upsert
  for (const p of list) {
    const now = new Date();

    // 매번 갱신되는 값
    const updateSet = {
      categoryIdx: p.category_idx ?? "null",
      isNew: p.is_new,
      trainingStatus: p.training_status,
      productLoadcellWeight: p.product_weight ?? "null",
      // eventPromotion은 “매번 갱신”이라고 했으니, 정책에 맞게 세팅
      // 만약 ProductList에서 프로모션 정보를 안 준다면, 여기서 덮어쓰면 안 될 수 있음.
      // => 초기값만 넣고 싶으면 아래 줄은 빼고 $setOnInsert로만 넣어.
      // eventPromotion: [],
    };

    // 최초 insert시에만 들어갈 값(초기 필드 세팅)
    // foldername/folderpath는 “초기 placeholder”로 만들어 넣어두는 형태
    const trainProductIdx = ++seq;
    const createDate = now;              // 스키마가 Date 타입이니 Date로 저장
    const updateDate = null;             // 아직 재촬영 안 했으면 null 유지
    const filelength = null;

    const stamp = FolderName(now);
    const engName = p.product_eng_name;
    const foldername = `${trainProductIdx}_${engName}_${stamp}`;
    const folderpath = `/chaiimage/productImg/${foldername}/`;

    await ProductUpload.updateOne(
      { productIdx: p.product_idx },
      {
        $set: updateSet,
        $setOnInsert: {
          // 고정
          productIdx: p.product_idx,
          productName: p.product_name,
          productEngName: p.product_eng_name,
          trainProductIdx,
          createDate,

          // 최초 생성 후로는 고정(재촬영/프로모션에서만 변경)
          foldername,
          folderpath,
          filelength,
          updateDate,

          // 배열 초기화
          eventPromotion: [],
        },
      },
      { upsert: true }
    );
  }

  await mongoose.disconnect();
  console.log(seq, "items processed.");
  console.log("[MongoDB] disconnected");
}

if (require.main === module) {
  main().catch((e) => {
    console.error("[ERROR]", e);
    process.exit(1);
  });
}
