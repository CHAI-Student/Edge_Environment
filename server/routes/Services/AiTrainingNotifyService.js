require("dotenv").config();
const { TrainingStore } = require("../routes/RestAPI/TrainingStore");

async function notifyTrainingStore({
  productIdx,
  productEngName,
  trainingStatus = "2",
} = {}) {
  if (!productIdx) throw new Error("productIdx is required");

  const res = await TrainingStore({
    productIdx,
    product_eng_name: productEngName,
    training_status: String(trainingStatus),
  });

  return {
    success: res?.result_cd === "S" || res?.DATA?.result_cd === "S",
    raw: res,
  };
}

async function notifyTrainingStoreMany(products = []) {
  const results = [];

  for (const p of products) {
    const result = await notifyTrainingStore({
      productIdx: p.productIdx,
      productEngName: p.productEngName,
      trainingStatus: p.trainingStatus || "2",
    });

    results.push({
      productIdx: p.productIdx,
      productEngName: p.productEngName,
      success: result.success,
      raw: result.raw,
    });
  }

  return results;
}

module.exports = {
  notifyTrainingStore,
  notifyTrainingStoreMany,
};
