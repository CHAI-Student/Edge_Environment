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
    // 서비스 API 설정 (minkyu 스타일)
    ioBoardUrl: process.env.IO_BOARD_URL || 'http://localhost:8001',
    cameraDriverUrl: process.env.CAMERA_DRIVER_URL || 'http://localhost:8003',
    productJudgeUrl: process.env.PRODUCT_JUDGE_URL || 'http://localhost:8002',
    modelUrl: process.env.MODEL_URL || 'http://localhost:8002',
    mqttClientUrl: process.env.MQTT_CLIENT_URL || 'http://localhost:8006',
    // yoona 스타일 API (HealthMqtt에서 사용)
    ioboardApi: process.env.IOBOARD_API || process.env.IO_BOARD_URL || 'http://localhost:8001',
    cameraApi: process.env.CAMERA_API || process.env.CAMERA_DRIVER_URL || 'http://localhost:8003',
    cardTerminalApi: process.env.CARD_TERMINAL_API || 'http://localhost:8004',
    modelApi: process.env.MODEL_API || process.env.MODEL_URL || 'http://localhost:8002',
    deadboltApi: process.env.DEADBOLT_API || process.env.IO_BOARD_URL || 'http://localhost:8001',
    // 레거시 호환
    ioboardApiHost: process.env.IO_BOARD_URL || 'http://io_board:8001',
    cameraControlApi: process.env.CAMERA_URL || 'http://localhost:8003',
    // 임베딩 모델 버전
    modelVersion: process.env.MODEL_VERSION || "v1.0.0",
}
