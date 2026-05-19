const FormData = require('form-data');
const config = require("../../config/dev");
const { v4: uuidv4 } = require("uuid");
const fs = require("fs");
const path = require("path");
const axios = require("axios");

const dummyImg = path.join(__dirname, "../../log/dummyTestImg.png");

function formatIfDate(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}`
         + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

async function sendToPNT(paymentResponse, inferenceResult, folderPath, paymentAt, CardMethod, productData) {
    console.log("[PNT] Preparing IF_08 data transfer...");
    // console.log('paymentResponse', paymentResponse)
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
        if (!fs.existsSync(dummyImg)) {
            throw new Error(`[PNT] Dummy image not found: ${dummyImg}`);
        }

        const fileName = path.basename(dummyImg);
        const stat = fs.statSync(dummyImg);
        const productMap = new Map(
            productData.map(p => [String(p.product_idx), p])
        );
        
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
        //   headers: { "Content-Type": "multipart/form-data" },
        });

        const timestamp = Date.now();
        const payload = {
            HEADER: {
                IF_ID: "IF_08",
                IF_SYSID: uuidv4(),
                IF_HOST: "CRKPNTCHAI", // 엑셀에는 EDGE라고 적혀있음
                // IF_DATE: timestamp,
                IF_DATE: formatIfDate(),
            },
            DATA:{
                device_idx: config.deviceIdx,
                division_idx: config.divisionIdx,
                token_id: paymentResponse.vankey_hash || paymentResponse.vankey,
                payment_at: paymentAt,
                approve_at: paymentResponse.authorization_date,
                approve_type: CardMethod === 'R' ? '2' : (CardMethod === 'S' ? '1' : '0'), // 0=일반카드, 1=삼성페이, 2=RFID
                approve_result: (paymentResponse === "Y")? 0 : 1,
                approve_price: inferenceResult.totalPrice,
                approve_no: paymentResponse.authorization_number,
                approve_card_issuer: paymentResponse.card_info.ISSUER_NAME,
                approve_card_num: paymentResponse.card_info.SERIAL_NUMBER,
                approve_card_json: JSON.stringify(paymentResponse),
                provider: "chai",
                state: inferenceResult.status === 'Y' ? '0' : '1',
                product_list: inferenceResult.products.map(p => {
                    const master = productMap.get(String(p.productId));

                    if (!master) {
                        console.warn(
                            `[PNT] Product master not found in IF_11: productId=${p.productId}. ` +
                            `Falling back to unitPrice for sale_price, 0 for supply_price.`
                        );
                    }

                    return {
                        product_idx: String(p.productId),
                        product_count: Number(p.count),
                        supply_price: Number(master?.supply_price ?? 0),
                        sale_price: Number(master?.sale_price ?? p.unitPrice ?? 0),
                    };
                }),
                // product_idx: inferenceResult.products.map(p => p.productId).join(","),
                // product_count: inferenceResult.products.map(p => p.count).join(","),
                payment_file_list: {
                    file_name: fileName,
                    file_ext: 'png',
                    file_size: stat.size,
                },
                // file_name: fileName,
                // // file_ext: 'mp4',
                // file_ext: 'png',
                // file_size: stat.size,
            }
        }
        // 3) FormData 구성 (payload + paymentFile)
        const form = new FormData();
        form.append("payload", JSON.stringify(payload), {
           contentType: "application/json"  // 추가
        });
        form.append("payment_file", fs.createReadStream(dummyImg), {
            filename: fileName,
            // contentType: "video/mp4",
            contentType: "image/png",
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
        console.log('response', response)
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