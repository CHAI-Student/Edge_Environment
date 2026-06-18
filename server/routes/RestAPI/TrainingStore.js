const axios = require("axios");
const config = require("../../config/dev");
const { v4: uuidv4 } = require("uuid");
const { divisionIdx } = require("../../config/prod");

let currentTrainingStatus = null;

function getTrainingStatus() {
  return currentTrainingStatus;
}

const external = axios.create({
  baseURL: config.restApi, // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

/**
 * [IF_07] 학습 진행 상태 전달
 */
async function TrainingStore(productMap, trainingStatus) {
    console.log(
        "MAKE TRAINING STORE FOR IF07::::",
        productMap, trainingStatus
    );
    // console.log(`MAKE TRAINING STORE FOR IF07:::: ${productIdx}, ${product_eng_name}, ${training_status}`)

    const normalizedTrainingStatus = String(trainingStatus);

    /*
    * Map은 JSON으로 직접 전송할 수 없으므로
    * product_list 배열로 변환합니다.
    */
    const productList = Array.from(productMap.values()).map(
            (product) => ({
                product_idx: String(product.product_idx),
                product_eng_name:product.product_eng_name,
                training_status:normalizedTrainingStatus,
            })
        );

    try {
        const token = process.env.JWT_TOKEN;
        if (!token) {
            throw new Error("JWT_TOKEN not set");
        }

        // 1. 정의서상 URL 경로 반영 (오타 수정) 
        const targetUrl = `${config.restApi}/chai/training/store`;

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
                product_list: productList,
                // product_list: [{
                //     product_idx: String(productIdx),
                //     product_eng_name: product_eng_name,
                //     training_status: String(training_status)
                // }],
            }
        };
        
        const response = await external.post(targetUrl, payload, {
            headers: {
                Authorization: `Bearer ${token}`,
            },
        });
        return response.data;

    } catch (error) {
        console.error(`[IF07] 통신 실패: ${error.message}`);
        console.error("[IF07] 통신 실패 status:", error.response?.status);
        console.error("[IF07] 통신 실패 data:", error.response?.data);
        throw error;
    }
}

module.exports = { TrainingStore, getTrainingStatus };