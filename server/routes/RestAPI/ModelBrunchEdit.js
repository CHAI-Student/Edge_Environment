const axios = require("axios");
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");
const { devAutoLogin } = require("../auth");

const external = axios.create({
  baseURL: config.restApi, // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

// 외부 API 호출 함수
async function ModelBrunchEdit({
  divisionIdx = config.divisionIdx,
  deviceIdx = null,
  productIdx = null,
} = {}) {
  const token = process.env.JWT_TOKEN;
  if (!token) {
    throw new Error("JWT_TOKEN not set");
  }

  const payload = {
    HEADER: {
      IF_ID: "IF_14",
      IF_SYSID: uuidv4(),
      IF_HOST: "CRKPNTCHAI",
      IF_DATE: Date.now(),
    },
    DATA: {
      device_list: [
        {
            division_idx: divisionIdx,
            device_idx: deviceIdx,
            brunch_name: 'FEB_001',
            brunch_update: Date.now(),
            model_version: "v"+'26.2.1',
            model_update_date: Date.now()
        }
      ]
    },
  };

  const r = await external.post("/chai/device/store", payload, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  return r.data;
}

module.exports = { ModelBrunchEdit };

// if (require.main === module) {
//   (async () => {
//     try {
//       console.log("[RestAPIClient] standalone start");
      
//       process.env.JWT_TOKEN = token;
//       process.env.JWT_TOKEN_AT = Date.now().toString();
//       console.log("[RestAPIClient] JWT_TOKEN set");

//       // REST API 호출
//       const data = await ModelBrunchEdit({
//         division_idx: config.divisionIdx,
//       });

//       console.log("[RestAPIClient] response:");
//       console.dir(data, { depth: null });
//     } catch (err) {
//       console.error("[RestAPIClient] error:");
//       console.error(err.message);
//       if (err.response) {
//         console.error(err.response.data);
//       }
//     }
//   })();
// }
