require("dotenv").config();
const { AnnotationLabel } = require("../../model/AnnotationLabel");

function randomHexColor() {
  const n = Math.floor(Math.random() * 0xffffff);
  return `#${n.toString(16).padStart(6, "0").toUpperCase()}`;
}

function uniqueColor(usedColors) {
  let c = randomHexColor();
  let guard = 0;

  while (usedColors.has(c) && guard < 10000) {
    c = randomHexColor();
    guard += 1;
  }

  if (guard >= 10000) throw new Error("Failed to generate unique HEX color");

  usedColors.add(c);
  return c;
}

async function syncAnnotationLabels({
  productModel,
  deleteMissing = false,
} = {}) {
  if (!productModel) {
    throw new Error("productModel is required");
  }

  const products = await productModel
    .find({}, { trainProductIdx: 1, productEngName: 1 })
    .lean();

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
      skipped += 1;
      continue;
    }

    desiredIds.add(id);

    const existed = existingById.get(id);
    const setOnInsert = existed ? {} : { color: uniqueColor(usedColors) };

    await AnnotationLabel.updateOne(
      { id },
      {
        $set: { name },
        ...(Object.keys(setOnInsert).length ? { $setOnInsert: setOnInsert } : {}),
      },
      { upsert: true }
    );

    upserted += 1;
  }

  let deleted = 0;
  if (deleteMissing) {
    const delRes = await AnnotationLabel.deleteMany({
      id: { $nin: Array.from(desiredIds) },
    });
    deleted = delRes?.deletedCount ?? 0;
  }

  return {
    totalProducts: products.length,
    desiredLabels: desiredIds.size,
    upserted,
    skipped,
    deleted,
  };
}

module.exports = {
  syncAnnotationLabels,
};
