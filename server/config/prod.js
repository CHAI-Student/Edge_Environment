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
    // MinIO 설정
    minioEndpoint: process.env.MINIO_ENDPOINT,
    minioPort: parseInt(process.env.MINIO_PORT) || 9000,
    minioAccessKey: process.env.MINIO_ACCESS_KEY,
    minioSecretKey: process.env.MINIO_SECRET_KEY,
    minioUseSSL: process.env.MINIO_USE_SSL === 'true',
    minioBucket: process.env.MINIO_BUCKET || 'chaiimage',
    // IO Board API 설정
    ioboardApiHost: process.env.IO_BOARD_URL || 'http://io_board:8001',
    doorControlEndpoint: '/api/door/control',
}