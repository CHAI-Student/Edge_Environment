module.exports = {
    mongoURI: process.env.MONGO_URI,
    mqttURL: process.env.MQTT_URL,
    mqttID: process.env.MQTT_USER,
    mqttPW: process.env.MQTT_PASS,

    divisionIdx: process.env.DIVISION_IDX,
    deviceIdx: process.env.DEVICE_IDX,

    restApi: process.env.REST_API,
    userId: process.env.USER_ID,
    userPassword: process.env.USER_PASSWORD,
    jwtToken: process.env.JWT_TOKEN,
    jwtTokenAt: process.env.JWT_TOKEN_AT,

    minioAccessKey: process.env.MINIO_ACCESS_KEY,
    minioSecretKey: process.env.MINIO_SECRET_KEY,
    minioURL: process.env.MINIO_URL,
    minioBucket: process.env.MINIO_BUCKET || 'chaiimage',
    sensorAPI: process.env.SENSOR_API,

    // ============================================
    // 서비스 API 설정 (통합)
    // ============================================
    // 기본 서비스 URL (환경변수 기반)
    ioBoardUrl: process.env.IO_BOARD_URL || 'http://localhost:8000',
    cameraDriverUrl: process.env.CAMERA_DRIVER_URL || 'http://localhost:8003',
    productJudgeUrl: process.env.PRODUCT_JUDGE_URL || 'http://localhost:8002',
    modelUrl: process.env.MODEL_URL || 'http://localhost:8002',
    mqttClientUrl: process.env.MQTT_CLIENT_URL || 'http://localhost:8006',
    cardTerminalUrl: process.env.CARD_TERMINAL_URL || 'http://localhost:8001',

    // 레거시 호환용 별칭 (HealthMqtt, Payments 등에서 사용)
    get ioboardApi() { return this.ioBoardUrl; },
    get cameraApi() { return this.cameraDriverUrl; },
    get modelApi() { return this.productJudgeUrl; },
    get deadboltApi() { return this.ioBoardUrl; },
    get cardTerminalApi() { return this.cardTerminalUrl; },
    get ioboardApiHost() { return this.ioBoardUrl; },
    get cameraControlApi() { return this.cameraDriverUrl; },

    // 임베딩 모델 버전
    modelVersion: process.env.MODEL_VERSION || "v1.0.0",
}
