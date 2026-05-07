// src/Process/ProductCollection.js
const config = require("../../config/key");
const { callApiToControlDeadbolt } = require('../Mqtt/DeadboltApiService');
const { DeadboltStatusAPI, LoadcellStatusAPI, CameraStatusAPI } = require('../Mqtt/HealthMqtt');
const { getClient } = require('../Mqtt/MqttClient');
const { ProductList } = require('../RestAPI/ProductList')
const { DeviceInfo } = require('../RestAPI/DeviceInfo')
const { ProductUpload } = require("../model/ProductUpload");
const { TrainingStore } = require("../RestAPI/TrainingStore");

const mongoose = require("mongoose");

let mongoConnectPromise = null;
async function ensureMongoConnected() {
  if (mongoose.connection.readyState === 1) return; // connected
  if (!mongoConnectPromise) {
    mongoConnectPromise = mongoose.connect(config.mongoURI);
  }
  await mongoConnectPromise;
}


const path = require('path');
const { v4: uuidv4 } = require("uuid");

function makeTimestampFolderName(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  const SS = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}${HH}${MM}${SS}`;
}

function fetchCurrentDoorState() {
    return new Promise((resolve, reject) => {
        const url = `${config.ioboardApi}/sse?streams=doors`;
        const evtSource = new EventSource(url);
        const timeout = setTimeout(() => {
            evtSource.close();
            console.warn("[DoorCheck] Timeout");
            resolve("UNKNOWN");
        }, 3000);

        evtSource.addEventListener('door.update', (event) => {
            if (!event.data) return;
            try {
                const data = JSON.parse(event.data);
                const rawState = data.deadbolt ? data.deadbolt.toUpperCase() : "";
                const closedStates = ["LOCK", "LOCKED", "CLOSE", "CLOSED"];
                const finalState = closedStates.includes(rawState) ? "CLOSE" : "OPEN";

                clearTimeout(timeout);
                evtSource.close();
                resolve(finalState);
            } catch (err) {
                clearTimeout(timeout);
                evtSource.close();
                resolve("UNKNOWN");
            }
        });
        evtSource.onerror = (err) => {
            clearTimeout(timeout);
            evtSource.close();
            resolve("UNKNOWN");
        };
    });
}

function ModelVersionUpdate(version) {
    // 1. 점(.)을 기준으로 분리하여 배열 생성
    const parts = version.split('.');

    // 2. 마지막 요소 추출 및 숫자 변환 후 +1
    const lastIndex = parts.length - 1;
    const lastValue = parseInt(parts[lastIndex], 10);

    // 3. 숫자가 아닌 경우(에러 방지)를 대비해 체크 후 업데이트
    if (!isNaN(lastValue)) {
        parts[lastIndex] = lastValue + 1;
    }

    // 4. 다시 점으로 이어붙여서 반환
    return parts.join('.');
}

async function ProductCollectionHealth() {
    const CameraStatus = await CameraStatusAPI(); // 예: '09'는 정상이라고 가정
    const DeadboltHealth = await DeadboltStatusAPI();
    const LoadcellHealth = await LoadcellStatusAPI();
    
    const isHealthOk = (CameraStatus === '09' && DeadboltHealth === '19' && LoadcellHealth === '29');
    isSuccess = isHealthOk;
    resultMsg = (isHealthOk) ? "status access" : "status error";

    return {CameraStatus, DeadboltHealth, LoadcellHealth, isSuccess, resultMsg}
}

async function DoorCollect() {
    const DoorCollect_SUB_TOPIC = `chai/device/${config.deviceIdx}/cmd/door/collect`;
    const DoorCollect_PUB_TOPIC = `chai/device/${config.deviceIdx}/ack/door/collect`;

    const client = getClient();

    client.on('connect', () => {
        client.subscribe(DoorCollect_SUB_TOPIC);
    });

    client.on('message', async (topic, message) => {
        if (topic !== DoorCollect_SUB_TOPIC) return;
        try {
            const payload = JSON.parse(message.toString());
            const reqData = payload.DATA;
            const reqDoorState = reqData.door_state;
            const reqStorageType = reqData.storage_type;
            const reqHasLoadCell = reqData.has_loadcell;
            
            const targetId = topic.split('/')[2];
            if (targetId !== config.deviceIdx && targetId !== '+') return;

            console.log(`[EdgePC] Request Received: ${reqData.door_state}`);
            
            // 요청 들어왔으니 수집 문열기 (*** 근데 어차피 다시 닫힐거 대비해서 IF06에서 다시 문여는데 여기서 열 필요가 있나)
            if (reqDoorState === 'OPEN') {
                const CurrentDoorState = await fetchCurrentDoorState();
                if (CurrentDoorState === "CLOSE") {
                    const folderPath = path.join(process.cwd(), "productImg") // 폴더 경로 지정
                    // [질문] 지금 해당 경로가 원본 데이터셋 폴더(상위 폴더) 경로이긴 한데
                    // 이 값이 IF06으로 전달되는 것도 아니고, IF04에서 폴더 경로를 픽앤탁에 보내야 하는 것도 아니고
                    // 어차피 IF06에서 상위 폴더/하위 폴더 경로까지 정해서 카메라 API로 전달하는데 여기서 꼭 지정해야할 필요가 있나?
                    const openResult = await callApiToControlDeadbolt("OPEN"); //문 열기 제어(데드볼트 열기)
                    
                    const { CameraStatus, DeadboltHealth, LoadcellHealth, isSuccess, resultMsg } = await ProductCollectionHealth();
                    const timestamp = makeTimestampFolderName();
                    const responsePayload = {
                        HEADER: {
                            IF_ID: "IF_04",
                            IF_SYSID: uuidv4(),
                            IF_HOST: "CRKPNTCCHAI",
                            IF_DATE: timestamp,
                        },
                        DATA: {
                            "division_idx": config.divisionIdx,
                            "device_idx": config.deviceIdx,
                            "door_state": await fetchCurrentDoorState(), // 혹시나 닫혔을 수도 있으니 실시간 값으로 반환
                            "storage_type": reqStorageType,
                            "has_loadcell": reqHasLoadCell,
                            "camera_status": (CameraStatus === '09') ? "1" : "0",
                            "deadbolt_status": (DeadboltHealth === '19') ? "1" : "0",
                            "loadcell_status": (LoadcellHealth === '29') ? "1" : "0",
                            "result_cd": isSuccess ? "S" : "F",
                            "result_msg": resultMsg
                        }
                };
                // ACK 전송
                client.publish(DoorCollect_PUB_TOPIC, JSON.stringify(responsePayload));
                }
                else{throw new Error("현재 문이 열려있는 상태입니다.");}
            }

            else if (reqDoorState === 'CLOSE') {
                const ProdictListResp = await ProductList({
                    division_idx: config.divisionIdx,
                    device_idx: config.deviceIdx,
                });
                const Products = ProdictListResp?.body?.products ?? [];
                
                const toUpdateIds = [];
                for (const p of Products) {
                    const isNew = String(p.is_new);
                    const training_status = String(p.training_status);

                    if (isNew === "0" && (training_status === "0" || training_status === "1")) {
                        p.training_status = "2";
                        if (p.product_idx != null) toUpdateIds.push(String(p.product_idx));
                        else console.log(`이상한 ProductIdx: ${p.product_idx}`);
                    }
                }

                if (!toUpdateIds.length) {console.log("[ProductCollection] CLOSE: 업데이트 대상 없음");
                    return;
                }

                let deviceList = await DeviceInfo();
                const myDevice = deviceList.find(device => device.device_idx === config.deviceIdx);
                let CurrentModelVersion = myDevice.model_version;
                console.log("[ProductCollection] 현재 모델 버전", CurrentModelVersion);
                // 불러온 모델의 버전 26.0.1이면 그냥 마지막 값에 +1 한 값(26.0.2)으로 업데이트하였음
                let UpdateModelVersion = ModelVersionUpdate(CurrentModelVersion);

                // MongoDB에 training_status 변화 저장/반영 및 모델 버전 업데이트
                await ensureMongoConnected();
                const result = await ProductUpload.updateMany(
                    { productIdx: { $in: toUpdateIds } },
                    { 
                        $set: { 
                            trainingStatus: "2",
                            modelVersion: UpdateModelVersion,
                            updateDate: new Date()
                        } 
                    }
                );
                console.log(`[ProductCollection] CLOSE: trainingStatus=2 반영 완료 (matched=${result.matchedCount}, modified=${result.modifiedCount})`);

                // 1:1 매핑 확인
                deviceList = await DeviceInfo();
                myDevice = deviceList.find(device => device.device_idx === config.deviceIdx);
                CurrentModelVersion = myDevice.model_version;
                
                // AI 서버 쪽으로 신규 상품이 전달되었음을 API로 전달
                for (let i = 0; i<deviceList.length; i++){
                    const ProductTrainingStore = await TrainingStore(
                        productIdx = deviceList[i].product_idx,
                        product_eng_name = deviceList[i].product_eng_name,
                        training_status = deviceList[i].training_status
                    );
                    const TrainingStoreRes = ProductTrainingStore.result_cd;
                    if (TrainingStoreRes === "S") {console.log(`[IF_07] ${i+1}번쨰 상품 성공: ${deviceList[i].product_eng_name}, 학습 상태: ${deviceList[i].training_status}`)}
                    else {console.log(`[IF_07] ${i+1}번쨰 상품 실패: ${deviceList[i].product_eng_name}, 학습 상태: ${deviceList[i].training_status}`)}
                }
            }

        } catch (error) {
            console.error("[EdgePC] Processing Error:", error);
        }
    });
}

module.exports = { DoorCollect, fetchCurrentDoorState, ProductCollectionHealth };