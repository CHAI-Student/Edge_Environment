// // src/Process/ProductCollection.js
// const config = require("../../config/key");
// const { DeviceInfo } = require('./DeviceInfo'); 
// const { callApiToControlDeadbolt } = require('../Mqtt/DeadboltApiService');
// const { DeadboltStatusAPI, LoadcellStatusAPI, CameraStatusAPI } = require('../Mqtt/HealthMqtt');
// const { AckCollect } = require('../Mqtt/AckCollect');
// const { DoorCollect } = require('../Mqtt/DoorCollect');
// const { MinIOUpload } = require('../../test/minioUpload');
// const { MongodbUpload } = require('../../test/mongodbUpload');

// const path = require('path');
// const { v4: uuidv4 } = require("uuid");

// function makeTimestampFolderName(d = new Date()) {
//   const yyyy = d.getFullYear();
//   const mm = String(d.getMonth() + 1).padStart(2, "0");
//   const dd = String(d.getDate()).padStart(2, "0");
//   const HH = String(d.getHours()).padStart(2, "0");
//   const MM = String(d.getMinutes()).padStart(2, "0");
//   const SS = String(d.getSeconds()).padStart(2, "0");
//   return `${yyyy}${mm}${dd}${HH}${MM}${SS}`;
// }

// function fetchCurrentDoorState() {
//     return new Promise((resolve, reject) => {
//         const url = `${config.ioboardApi}/sse?streams=doors`;
//         const evtSource = new EventSource(url);
//         const timeout = setTimeout(() => {
//             evtSource.close();
//             console.warn("[DoorCheck] Timeout");
//             resolve("UNKNOWN");
//         }, 3000);

//         evtSource.addEventListener('door.update', (event) => {
//             if (!event.data) return;
//             try {
//                 const data = JSON.parse(event.data);
//                 const rawState = data.deadbolt ? data.deadbolt.toUpperCase() : "";
//                 const closedStates = ["LOCK", "LOCKED", "CLOSE", "CLOSED"];
//                 const finalState = closedStates.includes(rawState) ? "CLOSE" : "OPEN";

//                 clearTimeout(timeout);
//                 evtSource.close();
//                 resolve(finalState);
//             } catch (err) {
//                 clearTimeout(timeout);
//                 evtSource.close();
//                 resolve("UNKNOWN");
//             }
//         });
//         evtSource.onerror = (err) => {
//             clearTimeout(timeout);
//             evtSource.close();
//             resolve("UNKNOWN");
//         };
//     });
// }

// async function ProductCollectionHealth() {
//     const CameraStatus = await CameraStatusAPI(); // 예: '09'는 정상이라고 가정
//     const DeadboltHealth = await DeadboltStatusAPI();
//     const LoadcellHealth = await LoadcellStatusAPI();
//     const CurrentDoorState = await fetchCurrentDoorState();
//     console.log(`[EdgePC] Physical Door: ${CurrentDoorState} / Request: ${reqData.door_state}`);
    
//     const isHealthOk = (CameraStatus === '09' && DeadboltHealth === '19' && LoadcellHealth === '29');
//     isSuccess = isHealthOk;
//     resultMsg = (isHealthOk) ? "status access" : "status error";

//     return {CameraStatus, DeadboltHealth, LoadcellHealth, CurrentDoorState, isSuccess, resultMsg}
// }

// async function ProductRegistration() {
//     const DoorCollect_SUB_TOPIC = `chai/device/${config.deviceIdx}/cmd/door/collect`;
//     const DoorCollect_PUB_TOPIC = `chai/device/${config.deviceIdx}/ack/door/collect`;

//     const client = getClient();

//     client.on('connect', () => {
//         client.subscribe(DoorCollect_SUB_TOPIC);
//     });

//     client.on('message', async (topic, message) => {
//         if (topic !== DoorCollect_SUB_TOPIC) return;  // ✅ 추가
//         try {
//             const payload = JSON.parse(message.toString());
//             const reqData = payload.DATA;
//             const reqDoorState = reqData.door_state;
            
//             // const targetId = topic.split('/')[2];
//             // if (targetId !== config.deviceIdx && targetId !== '+') return;

//             console.log(`[EdgePC] Request Received: ${reqData.door_state}`);
            
//             // 요청 들어왔으니 수집 문열기 (*** 근데 어차피 다시 닫힐거 대비해서 IF06에서 다시 문여는데 여기서 열 필요가 있나)
//             if (reqDoorState == 'CLOSE') {
//                 const openResult = await callApiToControlDeadbolt("OPEN"); //문 열기 제어(데드볼트 열기)
//             }
//             else{throw new Error("현재 문이 열려있는 상태입니다.");}
            
//             // 스냅샷 폴더 경로 지정
//             const timestamp = makeTimestampFolderName();
//             const folderPath = path.join(process.cwd(), "data_recordings", timestamp) // 폴더경로 지정(ex. /Edge_Environment/data_recordings/20260210_193325(상대경로로 표현하면))

//             const ProductSavePath = AckCollect(folderPath);

//             CameraStatus, DeadboltHealth, LoadcellHealth, CurrentDoorState, isSuccess, resultMsg = ProductCollectionHealth();
//             // [응답] 페이로드 구성
//             const responsePayload = {
//                 HEADER: {
//                     IF_ID: "IF_04",
//                     IF_SYSID: uuidv4(),
//                     IF_HOST: "CRKPNTCCHAI",
//                     IF_DATE: timestamp,
//                 },
//                 DATA: {
//                     "device_idx": config.deviceIdx,
//                     "division_idx": config.divisionIdx,
//                     "camera_status": (CameraStatus === '09') ? "1" : "0",
//                     "deadbolt_status": (DeadboltHealth === '19') ? "1" : "0",
//                     "loadcell_status": (LoadcellHealth === '29') ? "1" : "0",
//                     "result_cd": isSuccess ? "S" : "F",
//                     "result_msg": resultMsg
//                 }
//             };

//             // ACK 전송
//             client.publish(DoorCollect_PUB_TOPIC, JSON.stringify(responsePayload));
//             console.log(`[EdgePC] ACK Sent (Result: ${isSuccess ? 'S' : 'F'})`);

//         } catch (error) {
//             console.error("[EdgePC] Processing Error:", error);
//         }
//     });
// }

// module.exports = { ProductRegistration, fetchCurrentDoorState, ProductCollectionHealth };