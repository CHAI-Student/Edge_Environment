const config = require("../config/key");
const mongoose = require("mongoose");
require("dotenv").config();

const { AnnotationLabel } = require("../model/AnnotationLabel");

function randomHexColor() {
  const n = Math.floor(Math.random() * 0xffffff);
  return `#${n.toString(16).padStart(6, "0").toUpperCase()}`;
}

function uniqueColor(usedColors) {
  let c = randomHexColor();
  let guard = 0;
  while (usedColors.has(c) && guard < 10000) {
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

  // ✅ 모델 없이 컬렉션 직접 접근
  const productListCol = mongoose.connection.collection("ProductsList");

  // 필요한 필드만 projection
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

  // 기존 라벨(색 중복 방지)
  const existing = await AnnotationLabel.find({}, { id: 1, color: 1 }).lean();
  const usedColors = new Set(existing.map((x) => x.color).filter(Boolean));
  const existingById = new Map(existing.map((x) => [Number(x.id), x]));

  const desiredIds = new Set();
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
    const setOnInsert = existed ? {} : { color: uniqueColor(usedColors) };

    await AnnotationLabel.updateOne(
      { id },
      { $set: { name }, $setOnInsert: setOnInsert },
      { upsert: true }
    );

    upserted++;
  }

  // 삭제 정책(원치 않으면 주석 처리)
  const delRes = await AnnotationLabel.deleteMany({ id: { $nin: Array.from(desiredIds) } });

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