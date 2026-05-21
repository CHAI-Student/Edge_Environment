const axios = require("axios");
const config = require("../../config/dev");
const { v4: uuidv4 } = require("uuid");

const external = axios.create({
  baseURL: config.restApi, // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

/**
 * [IF_07] 학습 진행 상태 전달
 */
async function TrainingStore(productIdx, product_eng_name, training_status) {
    console.log(
        "MAKE TRAINING STORE FOR IF07::::",
        productIdx,
        product_eng_name,
        training_status
    );
    // console.log(`MAKE TRAINING STORE FOR IF07:::: ${productIdx}, ${product_eng_name}, ${training_status}`)
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
            // DATA: {
            //     division_idx: config.divisionIdx,
            //     device_idx: config.deviceIdx,
            //     product_idx: productIdx,
            //     product_eng_name: product_eng_name,
            //     training_status: training_status,
            //     result_cd: 'S',
            //     result_msg: `${product_eng_name} training data update is successful`
            // },
            DATA: {
                product_list: {
                    division_idx: config.divisionIdx,
                    device_idx: config.deviceIdx,
                    product_idx: String(productIdx),
                    product_eng_name: product_eng_name,
                    training_status: String(training_status)
                },
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
        throw error; 
    }
}

module.exports = { TrainingStore };