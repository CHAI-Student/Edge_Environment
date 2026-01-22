/**
 * Collect Door Control (수거함 도어 제어)
 * MQTT를 통한 수거함 도어 제어 핸들러
 */

const config = require('../../config/key');
const { callApiToControlDoor } = require('./DoorApiService');

/**
 * 수거함 도어 제어 핸들러
 * @param {object} message - MQTT 메시지
 * @returns {Promise<object>} - 응답 결과
 */
async function CollectDoor(message) {
    const deviceIdx = config.deviceIdx;
    const divisionIdx = config.divisionIdx;

    console.log(`[CollectDoor] Device: ${deviceIdx}, Division: ${divisionIdx}`);
    console.log(`[CollectDoor] Received message:`, message);

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
