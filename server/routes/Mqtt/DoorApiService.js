/**
 * Door API Service
 * Python 백엔드 API와 통신하여 도어 상태를 제어합니다.
 */

const axios = require('axios');
const config = require('../../config/key');

// API 설정
const API_HOST = 'http://localhost:8001';
const API_ENDPOINT = '/api/door/control';

/**
 * Door 상태 제어 API 호출
 * @param {string} targetState - "OPEN" 또는 "CLOSE"
 * @returns {Promise<object>} - API 응답
 */
async function callApiToControlDoor(targetState) {
    const url = `${API_HOST}${API_ENDPOINT}`;

    console.log(`[DoorApiService] Calling API: ${url} with state: ${targetState}`);

    try {
        const response = await axios.post(url, {
            action: targetState
        }, {
            timeout: 5000 // 5초 타임아웃
        });

        const finalState = response.data?.state || response.data?.status;
        console.log(`[DoorApiService] API response - Final state: ${finalState}`);

        return response.data;
    } catch (error) {
        if (error.response) {
            // 서버가 응답을 반환했지만 에러 상태코드
            console.error(`[DoorApiService] Server error: ${error.response.status}`);
            throw new Error(`Server responded with status ${error.response.status}`);
        } else if (error.request) {
            // 요청은 보냈지만 응답이 없음
            console.error('[DoorApiService] No response from server');
            throw new Error('No response from door control API');
        } else {
            // 요청 설정 중 에러
            console.error(`[DoorApiService] Error: ${error.message}`);
            throw error;
        }
    }
}

module.exports = { callApiToControlDoor };