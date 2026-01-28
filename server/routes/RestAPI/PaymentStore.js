const FormData = require('form-data');
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");

async function sendToPNT(paymentDate, paymentData, inferenceData, folderPath, token) {
    console.log("[PNT] Preparing IF_08 data transfer...");

    try {
        const formData = new FormData();
        const currentDate = new Date();
        const formattedDate = getFormatDate(currentDate);

        // --- [1] 이미지 파일 준비 (필수: payment_img_list) ---
        let paymentImgList = [];
        if (fs.existsSync(folderPath)) {
            const files = fs.readdirSync(`${folderPath}/cam_0`); // 상단 카메라 이미지를 고정적으로 보낸다는 가정
            // jpg, png 등 이미지 파일만 필터링
            const imageFiles = files.filter(file => /\.(jpg|jpeg|png)$/i.test(file)).slice(0, 2);

            paymentImgList = imageFiles.map(file => {
                const filePath = path.join(folderPath, file);
                const stats = fs.statSync(filePath);
                
                // [Binary] 실제 파일을 form-data의 'files' 키로 첨부
                // ※ 엑셀 명세에 따라 키 값('files' 또는 'image') 확인 필요
                formData.append('files', fs.createReadStream(filePath), { filename: file });

                return {
                    file_name: file,
                    file_ext: path.extname(file).replace('.', ''),
                    file_size: stats.size
                };
            });
        } else {
            console.warn(`[PNT] Warning: Image folder not found at ${folderPath}`);
        }

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
                
                // 결제 및 승인 일시 (응답 없을 시 현재 시간 대체)
                "payment_at": paymentDate,
                "approve_at": paymentData.authorization_date,
                
                "approve_type": "1",    // [필수 수정]
                "approve_result": "0",  // [필수 수정]
                "approve_price": inferenceData.totalPrice,
                "approve_no": paymentData.authorization_number,
                
                "approve_card_issuer": paymentData.card_info.issuer_name,
                "approve_card_num": paymentData.serial_number,
                
                "approve_card_json": JSON.stringify(paymentData),
                
                "provider": "chai",
                "state": paymentData.response_code,
                
                // [필수 수정] 상품 목록 (AI 모델 추론 결과 매핑)
                // 해당 탐지된 제품들의 productId notion에 적힌대로 나오는게 맞는지 확인
                "product_list": (inferenceData.products).map(p => ({
                    "product_idx": p.productId,
                    "product_count": p.count
                })),
                
                // [필수] 이미지 메타데이터 목록
                "payment_img_list": paymentImgList
            }
        };

        // --- [3] JSON 데이터를 'data' 필드에 추가 ---
        formData.append('data', JSON.stringify(jsonData));

        // --- [4] 서버 전송 ---
        // TODO: 엑셀 파일(IF_08.xlsx)에 명시된 API URL로 변경해 주세요.
        const pntUrl = `${config.restApi}/chai/payment/store`; 

        console.log(`[PNT] Sending to ${pntUrl} (Images: ${paymentImgList.length})`);

        const response = await axios.post(pntUrl, formData, {
            headers: {
                ...formData.getHeaders(), // Multipart Boundary 자동 설정
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

module.exports = { sendToPNT }