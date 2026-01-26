module.exports = {
    mongoURI:process.env.MONGO_URI,

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
    minioBucket: process.env.MINIO_BUCKET,
    
    ioboardApi: process.env.IOBOARD_API,
    cameraApi: process.env.CAMERA_API,
    cardTerminalApi: process.env.CARD_TERMINAL_API,
    modelApi: process.env.MODEL_API,

    modelVersion: process.env.MODEL_VERSION,
}