const { publish } = require("./MqttClient")
const config = require("../../config/key");
const { axios } = require("axios");

async function CollectDoor() {
    const deviceIdx = config.deviceIdx;
    const divisionIdx = config.divisionIdx;

    axios.post('/api/uploads/images', (req, res) => {
        const PRODUCT_IDX = "test01000121";
        const TS = "20251106_141029";
        const LOCAL_ROOT = path.resolve(process.cwd(), "server", "test", TS);
        const BUCKET = config.minioBucket;
    
        const minioClient = new Minio.Client({
            endPoint: config.minioURL,
            port: 9000,
            useSSL: false,
            accessKey: config.minioAccessKey,
            secretKey: config.minioSecretKey,
        });
    })
    
} 


module.exports = { CollectDoor };