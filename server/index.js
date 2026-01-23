const express = require("express");
const app = express();
const path = require("path");
const cors = require('cors')
const axios = require('axios');

const bodyParser = require("body-parser");
const cookieParser = require("cookie-parser");

require("dotenv").config({ path: path.resolve(__dirname, "../.env") });

const config = require("./config/key");

// 서비스 모듈 로드
const ioBoardSSE = require("./services/IOBoardSSESubscriber");
const configManager = require("./services/ConfigManager");
const scheduledLogger = require("./services/ScheduledLogger");

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
let minioClient = null;

if (config.minioURL && config.minioAccessKey) {
    minioClient = new Minio.Client({
        endPoint: config.minioURL,
        port: 9000,
        useSSL: false,
        accessKey: config.minioAccessKey,
        secretKey: config.minioSecretKey,
    });

    app.locals.minioClient = minioClient;
    app.locals.minioBucket = config.minioBucket || "chaiimage";

    (async () => {
        try {
            const buckets = await minioClient.listBuckets();
            console.log("[MINIO] Buckets:", buckets.map(b => b.name));
        } catch (err) {
            console.error("[MINIO] error:", err.message);
        }
    })();
} else {
    console.log('[MinIO] MinIO not configured, skipping connection');
}

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

// Products 라우트 (AIServer)
const productRouter = require("./routes/AIServer/Products");
app.use("/api", productRouter);

// MQTT 라우트
const mqttModule = require("./routes/mqtt");
const { disconnect } = require("./routes/Mqtt/MqttClient");
app.use('/', mqttModule.router);

// MQTT 초기화
mqttModule.init().catch((e) => {
    console.error('[APP] MQTT init during server start failed:', e?.message || e);
});

// Camera Control 라우트
const cameraRouter = require("./routes/camera");
app.use('/api/camera', cameraRouter);
console.log('[APP] Camera routes loaded');

// Door Control 라우트
const doorRouter = require("./routes/door");
app.use('/api/door', doorRouter);
console.log('[APP] Door routes loaded');

// Model 라우트
const modelRouter = require("./routes/model");
app.use('/api/model', modelRouter);
console.log('[APP] Model routes loaded');

// Logs 라우트
const logsRouter = require("./routes/logs");
app.use('/api/logs', logsRouter);
console.log('[APP] Logs routes loaded');

// Events 라우트 (SSE 포함)
const eventsModule = require("./routes/events");
app.use('/sse', eventsModule.router);
app.use('/api', eventsModule.router);
console.log('[APP] Events routes loaded');

// Dashboard 상태 API
app.get('/api/dashboard/status', async (req, res) => {
    try {
        const ioBoardClient = require("./services/IOBoardClient");
        const cameraClient = require("./services/CameraDriverClient");
        const productJudgeClient = require("./services/ProductJudgeClient");

        const [ioBoardHealthy, cameraHealthy, modelHealthy] = await Promise.all([
            ioBoardClient.isHealthy().catch(() => false),
            cameraClient.isHealthy().catch(() => false),
            productJudgeClient.isHealthy().catch(() => false)
        ]);

        res.json({
            status: 'ok',
            timestamp: new Date().toISOString(),
            services: {
                io_board: { healthy: ioBoardHealthy, port: 8001 },
                camera_driver: { healthy: cameraHealthy, port: 8003 },
                model: { healthy: modelHealthy, port: 8002 },
                node_server: { healthy: true, port: process.env.PORT || 8889 },
                mongodb: { connected: mongoose.connection.readyState === 1 }
            },
            io_board_sse: ioBoardSSE.getStatus(),
            config: configManager.getAllConfigs()
        });
    } catch (error) {
        res.status(500).json({
            status: 'error',
            error: error.message
        });
    }
});

// IO Board SSE 구독 시작
ioBoardSSE.start();
console.log('[APP] IO Board SSE subscriber started');

// 스케줄 로거 시작
scheduledLogger.start().catch(e => {
    console.error('[APP] ScheduledLogger start failed:', e.message);
});
console.log('[APP] Scheduled logger started');

// ============================================
// Static 파일 서빙
// ============================================
app.use('/products', express.static('uploads'));
app.use('/uploads/images', express.static('images'));
app.use('/images', express.static(path.join(__dirname, 'images')));

// Dashboard 정적 파일 서빙
app.use(express.static(path.resolve(__dirname, "../client/public")));

// Production 모드: React 빌드 서빙
if (process.env.NODE_ENV === "production") {
    app.use(express.static("client/build"));
    app.get("*", (req, res, next) => {
        if (req.path.startsWith('/api') || req.path.startsWith('/sse') || req.path.startsWith('/health')) {
            return next();
        }
        res.sendFile(path.resolve(__dirname, "../client", "build", "index.html"));
    });
}

// ============================================
// 서버 시작
// ============================================
const port = process.env.PORT || 8889

app.listen(port, () => {
    console.log(`[APP] Server Listening on ${port}`)
});

// ============================================
// Graceful Shutdown
// ============================================
async function gracefulShutdown(signal) {
    console.log(`\n[APP] ${signal} received. Shutting down...`);

    try {
        ioBoardSSE.stop();
        console.log('[APP] IO Board SSE subscriber stopped');
    } catch (e) {
        console.error('[APP] Error stopping IO Board SSE:', e.message);
    }

    try {
        scheduledLogger.stop();
        console.log('[APP] Scheduled logger stopped');
    } catch (e) {
        console.error('[APP] Error stopping Scheduled logger:', e.message);
    }

    try {
        await disconnect();
        console.log('[APP] MQTT disconnected');
    } catch (e) {
        console.error('[APP] Error disconnecting MQTT:', e.message);
    }

    if (mongoose.connection.readyState === 1) {
        await mongoose.connection.close();
        console.log('[DB] MongoDB disconnected');
    }

    process.exit(0);
}

process.on("SIGINT", () => gracefulShutdown("SIGINT"));
process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));
