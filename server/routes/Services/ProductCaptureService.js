// require("dotenv").config();
// const axios = require("axios");
// const config = require("../../config/key");

// /**
//  * 카메라 촬영 API 명세가 아직 확정되지 않은 경우를 대비해 optional hook으로 구성.
//  * config.cameraCaptureStartApi / config.cameraCaptureStopApi가 있으면 호출하고,
//  * 없으면 세션 정보만 반환한다.
//  */
// async function startProductCapture({ localRoot, timestamp, deviceIdx, cameras = ["cam_0", "cam_2"] } = {}) {
//   if (!localRoot) throw new Error("localRoot is required");

//   if (!config.cameraCaptureStartApi) {
//     console.log("[Capture] start skipped: config.cameraCaptureStartApi is not defined");
//     return { success: true, skipped: true, localRoot, timestamp, cameras };
//   }

//   const { data } = await axios.post(config.cameraCaptureStartApi, {
//     device_idx: deviceIdx,
//     local_root: localRoot,
//     timestamp,
//     cameras,
//   });

//   return data;
// }

// async function stopProductCapture({ localRoot, timestamp, deviceIdx, cameras = ["cam_0", "cam_2"] } = {}) {
//   if (!localRoot) throw new Error("localRoot is required");

//   if (!config.cameraCaptureStopApi) {
//     console.log("[Capture] stop skipped: config.cameraCaptureStopApi is not defined");
//     return { success: true, skipped: true, localRoot, timestamp, cameras };
//   }

//   const { data } = await axios.post(config.cameraCaptureStopApi, {
//     device_idx: deviceIdx,
//     local_root: localRoot,
//     timestamp,
//     cameras,
//   });

//   return data;
// }

// module.exports = {
//   startProductCapture,
//   stopProductCapture,
// };
