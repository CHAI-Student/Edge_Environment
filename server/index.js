const express = require("express");
const app = express();
const path = require("path");
const cors = require('cors')
const axios = require('axios');

const bodyParser = require("body-parser");
const cookieParser = require("cookie-parser");

require("dotenv").config({ path: path.resolve(__dirname, "../.env") });

const config = require("./config/key");

// ============================================
// MongoDB 연결
// ============================================
const mongoose = require("mongoose");
if (config.mongoURI) {
    mongoose.connect(config.mongoURI)
        .then(() => console.log('[DB] MongoDB Connected'))
        .catch(err => console.error('[DB] MongoDB connection error:', err.message));
} else {
    console.log('[DB] MongoDB URI not configured, skipping connection');
}

// ============================================
// MinIO 연결
// ============================================
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

// ============================================
// Middleware 설정
// ============================================
app.use(cors())
app.use(express.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());
app.use(cookieParser());

// 요청 로깅 (개발용)
app.use(function (req, res, next) {
    if (process.env.LOG_LEVEL === 'debug') {
        console.log(`[HTTP] ${req.method} ${req.path}`);
    }
    return next();
});

// ============================================
// Health Check Endpoint
// ============================================
app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        service: 'node_server',
        timestamp: new Date().toISOString(),
        mongodb: mongoose.connection.readyState === 1 ? 'connected' : 'disconnected',
        minio: minioClient ? 'configured' : 'not configured'
    });
});

// ============================================
// Routes 설정
// ============================================

// Auth 라우트
const authModule = require("./routes/auth");
app.use("/api/auth", authModule.router);

// 개발 환경 자동 로그인
(async () => {
    try {
        const token = await authModule.devAutoLogin();
    } catch (e) {
        console.error("[APP] dev auto login failed:", e?.message || e);
    }
})();

//use this to show the image you have in node js server to client (react js)
//https://stackoverflow.com/questions/48914987/send-image-path-from-node-js-express-server-to-react-client

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
app.use("/api", productsModule.router);

// MQTT 라우트
const mqttModule = require("./routes/mqtt");
const { disconnect } = require("./routes/Mqtt/MqttClient");
app.use('/', mqttModule.router);

// MQTT 초기화
mqttModule.init().catch((e) => {
    console.error('[APP] MQTT init during server start failed:', e?.message || e);
});

// ============================================
// Static 파일 서빙
// ============================================
// 상품 이미지 폴더
app.use('/products', express.static(path.join(__dirname, 'products')));
app.use('/images', express.static(path.join(__dirname, 'images')));

// Production 모드: React 빌드 서빙
if (process.env.NODE_ENV === "production") {
    app.use(express.static("client/build"));
    app.get("*", (req, res) => {
        res.sendFile(path.resolve(__dirname, "../client", "build", "index.html"));
    });
}

// ============================================
// 서버 시작
// ============================================
const port = process.env.PORT || 8888

app.listen(port, () => {
    console.log(`[APP] Server Listening on ${port}`)
});

// ============================================
// Graceful Shutdown
// ============================================
process.on("SIGINT", async () => {
    console.log("\n[APP] SIGINT received. Shutting down...");
    try { await disconnect(); } catch (e) { console.error(e); }
    if (mongoose.connection.readyState === 1) {
        await mongoose.connection.close();
        console.log('[DB] MongoDB disconnected');
    }
    process.exit(0);
});

process.on("SIGTERM", async () => {
    console.log("\n[APP] SIGTERM received. Shutting down...");
    try { await disconnect(); } catch (e) { console.error(e); }
    if (mongoose.connection.readyState === 1) {
        await mongoose.connection.close();
        console.log('[DB] MongoDB disconnected');
    }
    process.exit(0);
});
