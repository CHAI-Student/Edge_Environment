/**
 * Deadbolt API Service
 * Python 백엔드 API와 통신하여 데드볼트 상태를 제어합니다.
 */

const axios = require('axios');
const config = require('../../config/key');

// API 설정
const API_HOST = config.deadboltApi || config.ioboardApi || 'http://localhost:8001';
const API_ENDPOINT = '/deadbolt';

/**
 * Deadbolt 상태 제어 API 호출
 * @param {string} targetState - "OPEN" 또는 "CLOSE"
 * @returns {Promise<object>} - API 응답
 */
async function callApiToControlDeadbolt(targetState) {
    const DEADBOLT_API_URL = `${API_HOST}${API_ENDPOINT}`;

    console.log(`[DeadboltApiService] Calling API: ${DEADBOLT_API_URL} with state: ${targetState}`);

    try {
        const response = await axios.post(DEADBOLT_API_URL, {
            action: targetState
        }, {
            timeout: 5000 // 5초 타임아웃
        });

        const finalState = response.data?.state || response.data?.status;
        console.log(`[DeadboltApiService] API response - Final state: ${finalState}`);

        return response.data;
    } catch (error) {
        if (error.response) {
            // 서버가 응답을 반환했지만 에러 상태코드
            console.error(`[DeadboltApiService] Server error: ${error.response.status}`);
            throw new Error(`Server responded with status ${error.response.status}`);
        } else if (error.request) {
            // 요청은 보냈지만 응답이 없음
            console.error('[DeadboltApiService] No response from server');
            throw new Error('No response from deadbolt control API');
        } else {
            // 요청 설정 중 에러
            console.error(`[DeadboltApiService] Error: ${error.message}`);
            throw error;
        }
    }
}

module.exports = { callApiToControlDeadbolt };
