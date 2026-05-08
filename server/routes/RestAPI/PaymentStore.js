const FormData = require('form-data');
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");
const fs = require("fs");
const path = require("path");
const axios = require("axios");

const dummyImg = path.join(__dirname, "../../log/dummyTestImg.png");

async function sendToPNT(paymentResponse, inferenceResult, folderPath, paymentAt, CardMethod) {
    console.log("[PNT] Preparing IF_08 data transfer...");

    try {
        // 추후 카메라가 촬영한 영상으로 전송
        // const camFolderPath = path.join(folderPath, "archival", "cam_0");
        // const files = fs.readdirSync(camFolderPath);
        // const mp4 = files.find(f => f.toLowerCase().endsWith(".mp4"));
        // if (!mp4) {
        //     throw new Error("No mp4 file found in cam_0 folder");
        // }
        // const fullPath = path.join(camFolderPath, mp4);
        // const fileName = path.basename(fullPath);
        // const stat = fs.statSync(fullPath);

        // 더미 이미지로 전송
        if (!fs.existsSync(dummyImgPath)) {
            throw new Error(`[PNT] Dummy image not found: ${dummyImg}`);
        }

        const fileName = path.basename(dummyImg);
        const stat = fs.statSync(dummyImg);
        
        // if (fs.existsSync(camFolderPath)) {
        //     const files = fs.readdirSync(camFolderPath);
        //     const imageFiles = files.filter(file => /\.(jpg|jpeg|png)$/i.test(file)).slice(0, 2);

        //     paymentImgList = imageFiles.map(file => {
        //         const filePath = path.join(camFolderPath, file);
        //         const stats = fs.statSync(filePath);
                
        //         // 파일 스트림 첨부
        //         formData.append('files', fs.createReadStream(filePath), { filename: file });

        //         return {
        //             file_name: file,
        //             file_ext: path.extname(file).replace('.', ''),
        //             file_size: stats.size
        //         };
        //     });
        // } else {
        //     console.warn(`[PNT] Warning: Image folder not found at ${camFolderPath}`);
        // }


        // 결제 데이터 전달
        const external = axios.create({
          baseURL: config.restApi, // https://apichaidev.atcrk.co.kr/api/v1
          timeout: 10000,
          headers: { "Content-Type": "application/json" },
        });

        const timestamp = Date.now();
        const payload = {
            HEADER: {
                IF_ID: "IF_08",
                IF_SYSID: uuidv4(),
                IF_HOST: "CHAI",
                IF_DATE: timestamp,
            },
            DATA:{
                device_idx: config.deviceIdx,
                division_idx: config.divisionIdx,
                token_id: paymentResponse.vankey_hash || paymentResponse.vankey,
                payment_at: paymentAt,
                approve_at: paymentResponse.authorization_date,
                approve_type: CardMethod === 'R' ? '2' : (CardMethod === 'S' ? '1' : '0'), // 0=일반카드, 1=삼성페이, 2=RFID
                approve_result: 'SUCCESS',
                approve_price: inferenceResult.totalPrice,
                approve_no: paymentResponse.authorization_number,
                approve_card_issuer: paymentResponse.card_info.ISSUER_NAME,
                approve_card_num: paymentResponse.card_info.SERIAL_NUMBER,
                approve_card_json: JSON.stringify(paymentResponse),
                provider: "chai",
                state: inferenceResult.status === 'success' ? '0' : '1',
                product_idx: inferenceResult.products.map(p => p.productId).join(","),
                product_count: inferenceResult.products.map(p => p.count).join(","),
                file_name: fileName,
                // file_ext: 'mp4',
                file_ext: 'png',
                file_size: stat.size,
            }
        }
        // 3) FormData 구성 (payload + paymentFile)
        const form = new FormData();
        form.append("payload", JSON.stringify(payload));
        form.append("paymentFile", fs.createReadStream(fullPath), {
            filename: fileName,
            // contentType: "video/mp4",
            contentType: "image/jpeg",
        });

        const token = config.jwtToken
        const response = await external.post("/chai/payment/store", form, {
            headers: {
                ...form.getHeaders(),
                Authorization: `Bearer ${token}`,
            }, 
            timeout: 30000,
            maxBodyLength: Infinity,
            maxContentLength: Infinity,
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