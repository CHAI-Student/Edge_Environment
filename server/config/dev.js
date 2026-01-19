// 외부 API 접근에 쓰는 값들
module.exports = {
    mongoURI: '', // MongoDB로 연결
    // MQTT 브로커 접속
    mqttURL: 'mqtt://chaidev.atcrk.co.kr:1883',
    mqttID: 'pnt',
    mqttPW: 'chai',
    // 매장 번호
    divisionIdx: 'DI17647205538493077',
    // deviceIdx: 'DE17560868094789999',
    deviceIdx: 'DE17683631997086480',
    restApi: 'https://apichaidev.atcrk.co.kr/api/v1',
    userId: 'admin',
    userPassword: 'carrier041!',
    get jwtToken() {
        return process.env.JWT_TOKEN;
    },
    get jwtTokenAt() {
        return process.env.JWT_TOKEN_AT;
    },
}