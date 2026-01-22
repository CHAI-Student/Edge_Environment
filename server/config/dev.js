// 외부 API 접근에 쓰는 값들
module.exports = {
    mongoURI: process.env.MONGO_URI || 'mongodb://localhost:27017/chai',
    // MQTT 브로커 접속
    mqttURL: 'mqtt://chaidev.atcrk.co.kr:1883',
    mqttID: 'pnt',
    mqttPW: 'chai',
    // 매장 번호
    divisionIdx: 'DI17647205538493077',
    deviceIdx: 'DE17560868094789999',
    // deviceIdx: 'DE17683631997086480',
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
    // IO Board API 설정
    ioboardApiHost: process.env.IO_BOARD_URL || 'http://localhost:8001',
    doorControlEndpoint: '/api/door/control',
}