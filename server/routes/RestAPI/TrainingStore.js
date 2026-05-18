// src/Service/DeviceService.js
const axios = require("axios");
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");

/**
 * [IF_13] 장비 정보 조회 서비스
 */
async function TrainingStore(productIdx, product_eng_name, training_status) {
    try {
        // 1. 정의서상 URL 경로 반영 (오타 수정) 
        const targetUrl = `${config.restApi}/training/store`;

        // 현재 시간을 정의서 규격(YYYYMMDDHHMMSS)으로 변환
        const now = new Date();
        const formattedDate = now.toISOString().replace(/[-:T]/g, "").slice(0, 14);

        const payload = {
            HEADER: {
                IF_ID   : "IF_07",
                IF_SYSID: uuidv4(),
                IF_HOST : "CRKPNTCHAI",
                IF_DATE : formattedDate
            },
            DATA: {
                division_idx: config.divisionIdx,
                device_idx: config.deviceIdx,
                product_idx: productIdx,
                product_eng_name: product_eng_name,
                training_status: training_status,
                result_cd: 'S',
                result_msg: `${product_eng_name} training data update is successful`
            },
        };
        
        const response = await axios.post(targetUrl, payload);
        return response.data.DATA;

    } catch (error) {
        console.error(`[IF07] 통신 실패: ${error.message}`);
        throw error; 
    }
}

module.exports = { TrainingStore };