const FormData = require('form-data');
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");
const fs = require("fs");
const path = require("path");
const axios = require("axios");

// [수정 4] 날짜 포맷 함수 추가 (YYYY-MM-DD HH:mm:ss 형식 예시)
function getFormatDate(date) {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    const HH = String(date.getHours()).padStart(2, '0');
    const MM = String(date.getMinutes()).padStart(2, '0');
    const SS = String(date.getSeconds()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd} ${HH}:${MM}:${SS}`;
}

async function sendToPNT(paymentDate, paymentData, inferenceData, folderPath, token) {
    console.log("[PNT] Preparing IF_08 data transfer...");

    try {
        const formData = new FormData();
        const currentDate = new Date();
        const formattedDate = getFormatDate(currentDate);

        // --- 이미지 파일 준비 ---
        let paymentImgList = [];

        const camFolderPath = path.join(folderPath, "images", "cam_0");

        if (fs.existsSync(camFolderPath)) {
            const files = fs.readdirSync(camFolderPath);
            const imageFiles = files.filter(file => /\.(jpg|jpeg|png)$/i.test(file)).slice(0, 2);

            paymentImgList = imageFiles.map(file => {
                const filePath = path.join(camFolderPath, file);
                const stats = fs.statSync(filePath);

                // 파일 스트림 첨부
                formData.append('files', fs.createReadStream(filePath), { filename: file });

                return {
                    file_name: file,
                    file_ext: path.extname(file).replace('.', ''),
                    file_size: stats.size
                };
            });
        } else {
            console.warn(`[PNT] Warning: Image folder not found at ${camFolderPath}`);
        }

        const cardInfo = paymentData.card_info;

        const jsonData = {
            "HEADER": {
                "IF_ID": "IF_08",
                "IF_SYSID": uuidv4(),
                "IF_HOST": "EDGE",
                "IF_DATE": formattedDate
            },
            "DATA": {
                "device_idx": config.deviceIdx,
                "division_idx": config.divisionIdx,
                "token_id": token,

                "payment_at": paymentDate,
                "approve_at": paymentData.authorization_date,

                "approve_type": "1", // [필수 수정]
                "approve_result": "0", // [필수 수정]
                "approve_price": inferenceData.totalPrice,
                "approve_no": paymentData.authorization_number,

                "approve_card_issuer": cardInfo.ISSUER_NAME,
                "approve_card_num": cardInfo.SERIAL_NUMBER,

                "approve_card_json": JSON.stringify(paymentData),

                "provider": "chai",
                "state": paymentData.response_code,

                // [필수 수정] 상품 목록 (AI 모델 추론 결과 매핑)
                // 해당 탐지된 제품들의 productId notion에 적힌대로 나오는게 맞는지 확인
                "product_list": (inferenceData.products || []).map(p => ({
                    "product_idx": p.productId,
                    "product_count": p.count
                })),

                "payment_img_list": paymentImgList
            }
        };

        // --- [3] JSON 데이터 추가 ---
        formData.append('data', JSON.stringify(jsonData));

        // --- [4] 서버 전송 ---
        const pntUrl = `${config.restApi}/chai/payment/store`;

        console.log(`[PNT] Sending to ${pntUrl} (Images: ${paymentImgList.length})`);

        const response = await axios.post(pntUrl, formData, {
            headers: {
                ...formData.getHeaders(),
            },
            maxContentLength: Infinity,
            maxBodyLength: Infinity
        });

        if (response.status === 200) {
            console.log("[PNT] Transfer Success:", response.data);
            return true;
        } else {
            console.error(`[PNT] Transfer Failed (Status: ${response.status})`);
            return false;
        }

    } catch (error) {
        console.error("[PNT] Error:", error.message);
        if (error.response) {
            console.error("[PNT] Server Response:", error.response.data);
        }
        return false;
    }
}

module.exports = { sendToPNT };
