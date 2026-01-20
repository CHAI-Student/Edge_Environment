const { publish } = require("./MqttClient")
const config = require("../../config/key");

async function CollectDoor() {
    const deviceIdx = config.deviceIdx;
    const divisionIdx = config.divisionIdx;
    
} 


module.exports = { CollectDoor };