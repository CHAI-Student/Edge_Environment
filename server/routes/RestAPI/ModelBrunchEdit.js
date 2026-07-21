// ============================================================
// ModelBrunchEdit.js
// 역할: 클라우드(PNT/CHAI) REST API IF_14(장비 정보 저장) 호출 모듈.
//  - /chai/device/store 에 device_list(brunch_name, brunch_update,
//    model_version, model_update_date)를 담아 POST 하여 장비의
//    model brunch 정보를 갱신(edit)한다.
//  - 인증은 config.jwtToken(Bearer) 사용.
// ============================================================
const axios = require("axios");
const config = require("../../config/key");
const { v4: uuidv4 } = require("uuid");

// IF 규격(YYYYMMDDHHMMSS)의 날짜 문자열 생성
function formatIfDate(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}`
         + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

const external = axios.create({
  baseURL: config.restApi, // https://apichaidev.atcrk.co.kr/api/v1
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

// 외부 API 호출 함수
// [IF_14] 장비의 model brunch / model version 정보를 클라우드에 저장(갱신)
async function ModelBrunchEdit({
  divisionIdx = config.divisionIdx,
  deviceIdx = null,
  productIdx = null,
} = {}) {
  const token = config.jwtToken;
  if (!token) {
    throw new Error("JWT_TOKEN not set");
  }

  const payload = {
    HEADER: {
      IF_ID: "IF_14",
      IF_SYSID: uuidv4(),
      IF_HOST: "CRKPNTCHAI",
      IF_DATE: formatIfDate(),
    },
    DATA: {
      device_list: [
        {
            division_idx: divisionIdx,
            device_idx: deviceIdx,
            brunch_name: 'FEB_001',
            brunch_update: formatIfDate(),
            model_version: "v"+'26.2.1',
            model_update_date: formatIfDate()
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
