// ============================================================
// mongoDBAnnotationUpload.js — 수동 실행용 테스트 스크립트
// 역할: MongoDB ProductsList를 기준으로 AnnotationLabel 컬렉션을 동기화
//       (id=0 hand label 고정 upsert, 상품별 label upsert + 랜덤 색상 배정,
//       잔여 label 삭제)하는 흐름을 단독 실행으로 검증한다.
// ============================================================
const config = require("../config/key");
const mongoose = require("mongoose");
require("dotenv").config();

const { AnnotationLabel } = require("../model/AnnotationLabel");

const fixedLabel = {
  id: 0,
  name: "hand",
  color: "#F08CB3",
  attributes: [],
  type: "any",
};

function randomHexColor() {
  const n = Math.floor(Math.random() * 0xffffff);
  return `#${n.toString(16).padStart(6, "0").toUpperCase()}`;
}

function uniqueColor(usedColors) {
  let c = randomHexColor();
  let guard = 0;

  while ((usedColors.has(c) || c === fixedLabel.color) && guard < 10000) {
    c = randomHexColor();
    guard++;
  }

  if (guard >= 10000) throw new Error("Failed to generate unique HEX color");

  usedColors.add(c);
  return c;
}

async function main() {
  await mongoose.connect(config.mongoURI);
  console.log("[MongoDB] connected");

  // 고정 hand label upsert
  await AnnotationLabel.updateOne(
    { id: fixedLabel.id },
    {
      $set: {
        name: fixedLabel.name,
        color: fixedLabel.color,
        attributes: fixedLabel.attributes,
        type: fixedLabel.type,
      },
    },
    { upsert: true }
  );

  const productListCol = mongoose.connection.collection("ProductsList");

  const products = await productListCol
    .find({}, { projection: { trainProductIdx: 1, productEngName: 1 } })
    .toArray();

  console.log("[ProductList] items:", products.length);

  if (!products.length) {
    await mongoose.disconnect();
    console.log("[MongoDB] disconnected");
    return;
  }

  console.log("[ProductList] sample:", products[0]);

  const existing = await AnnotationLabel.find({}, { id: 1, color: 1 }).lean();

  const usedColors = new Set(existing.map((x) => x.color).filter(Boolean));
  usedColors.add(fixedLabel.color);

  const existingById = new Map(existing.map((x) => [Number(x.id), x]));

  const desiredIds = new Set([fixedLabel.id]);

  let upserted = 0;
  let skipped = 0;

  for (const p of products) {
    const id = Number(p.trainProductIdx);
    const name = p.productEngName ? String(p.productEngName).trim() : "";

    if (!Number.isFinite(id) || !name) {
      skipped++;
      continue;
    }

    desiredIds.add(id);

    const existed = existingById.get(id);
    const setOnInsert = existed
      ? {}
      : {
          color: uniqueColor(usedColors),
          attributes: [],
          type: "any",
        };

    await AnnotationLabel.updateOne(
      { id },
      {
        $set: { name },
        ...(Object.keys(setOnInsert).length
          ? { $setOnInsert: setOnInsert }
          : {}),
      },
      { upsert: true }
    );

    upserted++;
  }

  const delRes = await AnnotationLabel.deleteMany({
    id: { $nin: Array.from(desiredIds) },
  });

  await mongoose.disconnect();

  console.log("[SYNC DONE]", {
    totalProducts: products.length,
    desiredLabels: desiredIds.size,
    upserted,
    skipped,
    deleted: delRes?.deletedCount ?? 0,
  });

  console.log("[MongoDB] disconnected");
}

if (require.main === module) {
  main().catch((e) => {
    console.error("[ERROR]", e);
    process.exit(1);
  });
}