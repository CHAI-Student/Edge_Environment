// 외부 API 접근에 쓰는 값들
module.exports = {
    mongoURI: 'mongodb://admin:%40crkchai2025@139.150.81.182:27017/CHAI?authSource=admin', // MongoDB로 연결
    //MINIO 연결
    minioAccessKey: 'admin',
    minioSecretKey: 'CrkMinio2026',
    minioURL: '139.150.8.82',
    minioBucket: 'chaiimage',
    // MQTT 브로커 접속
    mqttURL: 'mqtt://chaidev.atcrk.co.kr:1883',
    mqttID: 'pnt',
    mqttPW: 'chai',
    // 매장 고유번호
    divisionIdx: 'DI17647205538493077',
    // 장비 고유번호
    // deviceIdx: 'DE17560868094789999',
    deviceIdx: 'DE17683631997086480',
    // PNT RestAPI 연결
    restApi: 'https://apichaidev.atcrk.co.kr/api/v1',
    userId: 'chai',
    userPassword: 'carrier041!',
    get jwtToken() {
        return process.env.JWT_TOKEN;
    },
    get jwtTokenAt() {
        return process.env.JWT_TOKEN_AT;
    },
    doorControlApi: "http://localhost:8000",
}