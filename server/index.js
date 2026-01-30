const express = require("express");
const app = express();
const path = require("path");
const cors = require('cors')
const axios = require('axios');

const bodyParser = require("body-parser");
const cookieParser = require("cookie-parser");

require("dotenv").config();

const config = require("./config/key");

//mongoDB 연결
const mongoose = require("mongoose");
mongoose
  .connect(config.mongoURI)
  .then(() => console.log("[MONGO-DB] DB connected"))
  .catch(err => console.error(err));

//MinIO 연결
const Minio = require("minio");

const minioClient = new Minio.Client({
  endPoint: config.minioURL,
  port: 9000,
  useSSL: false,
  accessKey: config.minioAccessKey,
  secretKey: config.minioSecretKey,
});

app.locals.minioClient = minioClient;
app.locals.minioBucket = "chaiimage"; // 또는 config로

(async () => {
  try {
    const buckets = await minioClient.listBuckets();
    console.log("[MINIO] Buckets:", buckets);
  } catch (err) {
    console.error("[MINIO] error:", err);
  }
})();

app.use(cors())
app.use(express.json());

//to not get any deprecation warning or error
//support parsing of application/x-www-form-urlencoded post data
app.use(bodyParser.urlencoded({ extended: true }));
//to get json data
// support parsing of application/json type post data
app.use(bodyParser.json());
app.use(cookieParser());

// console.log(process.env.NODE_ENV)
app.use(function (req, res, next) {
  // console.log(req);
  return next();
})

// app.use('/api/users', require('./routes/users'));
// app.use('/api/upload', require('./routes/upload'));
const authModule = require("./routes/auth");
// app.use("/api/auth", authModule.router);

(async () => {
  try {
    await authModule.devAutoLogin();
  } catch (e) {
    console.error("[APP] dev auto login failed:", e?.message || e);
  }
})();


//use this to show the image you have in node js server to client (react js)
//https://stackoverflow.com/questions/48914987/send-image-path-from-node-js-express-server-to-react-client
const paymentRouter = require("./routes/RestAPI/Payments");

// app.use('/payment', paymentRouter.router)
(async () => {
  try {
    // await authModule.devAutoLogin();
    await paymentRouter.init();
  } catch (e) {
    console.error("[APP] dev auto payment failed:", e?.message || e);
  }
})();

const productRouter = require("../server/routes/AIServer/Products"); // 네 라우터 파일 경로
app.use("/api", productRouter);
app.use('/products', express.static('uploads'));
app.use('/uploads/images', express.static('images'));

// Serve static assets if in production
if (process.env.NODE_ENV === "production") {

  // Set static folder   
  // All the javascript and css files will be read and served from this folder
  app.use(express.static("client/build"));

  // index.html for all page routes    html or routing and naviagtion
  app.get("*", (req, res) => {
    res.sendFile(path.resolve(__dirname, "../client", "build", "index.html"));
  });
}

const port = process.env.PORT || 8888

// MQTT 
// 라우터 및 초기화
const mqttModule = require("./routes/mqtt");
const { disconnect } = require("./routes/Mqtt/MqttClient");

// 마운트된 라우터 (예: /api/publish)
app.use('/', mqttModule.router);

// 서버 시작 전에 MQTT 초기화 시도
mqttModule.init().catch((e) => {
  console.error('[APP] MQTT init during server start failed:', e?.message || e);
});

app.listen(port, () => {
  console.log(`Server Listening on ${port}`)
});

// Graceful shutdown for MQTT client
process.on("SIGINT", async () => {
  console.log("\n[APP] SIGINT received. Shutting down...");
  try { await disconnect(); } catch (e) { console.error(e); }
  process.exit(0);
});

process.on("SIGTERM", async () => {
  console.log("\n[APP] SIGTERM received. Shutting down...");
  try { await disconnect(); } catch (e) { console.error(e); }
  process.exit(0);
});

// const paymentRouter = require("./routes/RestAPI/Payments");

// (async () => {
//   try {
//     // const token = await authModule.devAutoLogin();
//     await paymentRouter.init();
//   } catch (e) {
//     console.error("[APP] dev auto login failed:", e?.message || e);
//   }
// })();