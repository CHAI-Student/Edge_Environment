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
    userId: 'chaitest',   
    // userId: 'chaitest2',    
    userPassword: 'iljin123!',
    get jwtToken() {
        return process.env.JWT_TOKEN;
    },
    get jwtTokenAt() {
        return process.env.JWT_TOKEN_AT;
    },
    // IO Board API 설정(로드셀, 데드볼트)
    ioboardApi: 'http://localhost:8000',
    // 카메라 서버 API 설정
    cameraApi: "http://localhost:8003",
    // 카드단말기 서버 API 설정
    cardTerminalApi: "http://localhost:8001",
    // 모델 서버 API 설정
    modelApi: "http://localhost:8002",

    // 임베딩 모델 버전
    modelVersion: "v1.0.0",
}