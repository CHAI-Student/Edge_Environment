// 외부 API 접근에 쓰는 값들
module.exports = {
    mongoURI: process.env.MONGO_URI || 'mongodb://localhost:27017/chai',
    // MQTT 브로커 접속
    mqttURL: 'mqtt://chaidev.atcrk.co.kr:1883',
    mqttID: 'pnt',
    mqttPW: 'chai',
    // 매장 번호
    divisionIdx: 'DI17647205538493077',
    // 장비 고유번호
    deviceIdx: 'DE17560868094789999',
    // deviceIdx: 'DE17683631997086480',
    // PNT RestAPI 연결
    restApi: 'https://apichaidev.atcrk.co.kr/api/v1',
    userId: 'admin',
    userPassword: 'carrier041!',
    get jwtToken() {
        return process.env.JWT_TOKEN;
    },
    get jwtTokenAt() {
        return process.env.JWT_TOKEN_AT;
    },
    // MinIO 설정
    minioEndpoint: process.env.MINIO_ENDPOINT || 'localhost',
    minioPort: parseInt(process.env.MINIO_PORT) || 9000,
    minioAccessKey: process.env.MINIO_ACCESS_KEY || 'minioadmin',
    minioSecretKey: process.env.MINIO_SECRET_KEY || 'minioadmin',
    minioUseSSL: process.env.MINIO_USE_SSL === 'true',
    minioBucket: process.env.MINIO_BUCKET || 'chaiimage',
    minioURL: process.env.MINIO_URL || 'localhost',
    // 서비스 API 설정
    ioBoardUrl: process.env.IO_BOARD_URL || 'http://localhost:8001',
    cameraDriverUrl: process.env.CAMERA_DRIVER_URL || 'http://localhost:8003',
    productJudgeUrl: process.env.PRODUCT_JUDGE_URL || 'http://localhost:8002',
    modelUrl: process.env.MODEL_URL || 'http://localhost:8002',
    mqttClientUrl: process.env.MQTT_CLIENT_URL || 'http://localhost:8006',
    // 레거시 호환
    ioboardApiHost: process.env.IO_BOARD_URL || 'http://localhost:8001',
    cameraControlApi: process.env.CAMERA_URL || 'http://localhost:8003',
    doorControlEndpoint: '/api/door/control',
}
