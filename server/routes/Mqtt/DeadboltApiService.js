// 파일명: DoorApiService.js
const axios = require("axios");
const config = require("../../config/key");

const API_HOST = config.ioboardApi; // 기본값 설정
const API_ENDPOINT = "/deadbolt"; // 상세 경로

const { DeadboltTerminalErrorState } = require("./HealthMqtt");

/**
 * API 서버에 도어 제어 요청을 보냅니다.
 * Python 서버의 스펙: POST /deadbolt, Body: { "state": "OPEN" | "CLOSE" }
 * @param {string} targetState - "OPEN" or "CLOSE"
 * @returns {Promise<string>} - 서버가 반환한 최종 상태 ("OPEN" or "CLOSE")
 */
async function callApiToControlDeadbolt(targetState) {
  const DEADBOLT_API_URL = `${API_HOST}${API_ENDPOINT}`;
  try {
    console.log(`[API] Sending Request to ${DEADBOLT_API_URL} (state: ${targetState})...`);

    // POST 요청 전송
    const response = await axios.post(DEADBOLT_API_URL, {
      action: targetState 
    }, {
      timeout: 5000 // 5초 타임아웃
    });
    // console.log(response)

    // API 응답 확인
    const finalState = response.data.state;
    console.log(`[API] Response Received. Final State: ${finalState}`);

    // 데드볼트 작동 불량인 경우 --> 요청한 값에서 변화가 없는 경우 error 처리
    const expectedState = targetState === "OPEN" ? "UNLOCK" : "LOCK";
    console.log("targetState =", targetState);
    console.log("finalState =", finalState);
    console.log("expectedState =", expectedState);
    if (finalState !== expectedState) {
      DeadboltTerminalErrorState("11");
      throw new Error(
        `Deadbolt operation failed. target=${targetState}, expected=${expectedState}, final=${finalState}`
      );}

return finalState;
    
    return finalState;

  } catch (error) {
    // 에러 발생 시 상세 내용 처리
    if (error.response) {
      throw new Error(`Server Error (${error.response.status}): ${JSON.stringify(error.response.data)}`);
    } else if (error.request) {
      throw new Error("No response from server (Network Error)");
    } else {
      throw new Error(error.message);
    }
  }
}

module.exports = { callApiToControlDeadbolt };