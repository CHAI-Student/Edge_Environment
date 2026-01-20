const config = require("../config/key");
const mongoose = require("mongoose");
const { ProductUpload } = require("../model/ProductUpload");

require("dotenv").config();

async function main() {
  await mongoose.connect(config.mongoURI);
  console.log("[MongoDB] connected");

  const doc = await ProductUpload.create({
    productIdx: "TEST_PRODUCT_003",
    divisionIdx: "TEST_DIVISION_003",
    modelVersion: "v0.0.1",
    brunchName: "dev",
    productName: "테스트 상품",
    categoryIdx: "TEST_CAT",
    isNew: "Y",
    trainingStatus: "UPLOADED",
    productEngName: "Test Product",
    productLoadcellWeight: "123g",

    foldername: "TEST_FOLDER_20260120_1706",
    folderpath: "s3://chaiimage/TEST_FOLDER_20260120_1706/",
    filelength: 3,

    eventPromotion: ["test"],
  });

  console.log("Inserted _id:", doc._id.toString());
  await mongoose.disconnect();
  console.log("[MongoDB] disconnected");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
