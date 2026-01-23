const config = require('../../config/key');
const { callApiToControlDoor } = require('./DoorApiService');
const { publish } = require("./MqttClient")
const { axios } = require("axios");

async function CollectDoor(message) {
    const deviceIdx = config.deviceIdx;
    const divisionIdx = config.divisionIdx;

    console.log(`[CollectDoor] Device: ${deviceIdx}, Division: ${divisionIdx}`);
    console.log(`[CollectDoor] Received message:`, message);
  
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

    try {
        const action = message?.action || message?.command;

        if (!action) {
            throw new Error('Action not specified in message');
        }

        const targetState = action.toUpperCase();

        if (targetState !== 'OPEN' && targetState !== 'CLOSE') {
            throw new Error(`Invalid action: ${action}. Must be OPEN or CLOSE`);
        }

        const result = await callApiToControlDoor(targetState);

        return {
            success: true,
            deviceIdx,
            divisionIdx,
            action: targetState,
            result
        };
    } catch (error) {
        console.error(`[CollectDoor] Error: ${error.message}`);
        return {
            success: false,
            deviceIdx,
            divisionIdx,
            error: error.message
        };
    }
}

module.exports = { CollectDoor };
