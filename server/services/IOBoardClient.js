/**
 * IOBoardClient - Python io_board 서비스 HTTP 클라이언트
 *
 * IO Board FastAPI 서버(port 8000)와 통신하여
 * 데드볼트 제어, 로드셀 조회 등을 수행합니다.
 */

const axios = require('axios');
const config = require('../config/key');

class IOBoardClient {
    constructor() {
        this.baseUrl = config.ioBoardUrl || 'http://localhost:8000';
        this.timeout = 5000; // 5초 타임아웃
    }

    /**
     * 데드볼트 상태 설정
     * @param {string} state - 'OPEN' 또는 'CLOSE'
     * @returns {Promise<{state: string}>} 실제 상태
     */
    async setDeadbolt(state) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/deadbolt`,
                { state },
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[IOBoardClient] setDeadbolt error:', error.message);
            throw new Error(`IO Board deadbolt control failed: ${error.message}`);
        }
    }

    /**
     * 로드셀 값 조회 (10채널)
     * @returns {Promise<string[]>} 로드셀 값 배열
     */
    async getLoadcells() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/loadcells`,
                { timeout: this.timeout }
            );
            return response.data.loadcells;
        } catch (error) {
            console.error('[IOBoardClient] getLoadcells error:', error.message);
            throw new Error(`IO Board loadcell query failed: ${error.message}`);
        }
    }

    /**
     * 문/데드볼트 상태 조회
     * @returns {Promise<{door: string, deadbolt: string}>}
     */
    async getStatus() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/status`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[IOBoardClient] getStatus error:', error.message);
            throw new Error(`IO Board status query failed: ${error.message}`);
        }
    }

    /**
     * IO Board 초기화
     */
    async init() {
        try {
            await axios.post(
                `${this.baseUrl}/init`,
                {},
                { timeout: this.timeout }
            );
            return { success: true };
        } catch (error) {
            console.error('[IOBoardClient] init error:', error.message);
            throw new Error(`IO Board init failed: ${error.message}`);
        }
    }

    /**
     * 로드셀 영점 캘리브레이션
     */
    async calibrate() {
        try {
            await axios.post(
                `${this.baseUrl}/calibrate`,
                {},
                { timeout: this.timeout }
            );
            return { success: true };
        } catch (error) {
            console.error('[IOBoardClient] calibrate error:', error.message);
            throw new Error(`IO Board calibration failed: ${error.message}`);
        }
    }

    /**
     * 에러 히스토리 조회
     * @returns {Promise<Array<{code: string}>>}
     */
    async getErrors() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/errors`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[IOBoardClient] getErrors error:', error.message);
            throw new Error(`IO Board error query failed: ${error.message}`);
        }
    }

    /**
     * 에러 히스토리 클리어
     */
    async clearErrors() {
        try {
            await axios.delete(
                `${this.baseUrl}/errors`,
                { timeout: this.timeout }
            );
            return { success: true };
        } catch (error) {
            console.error('[IOBoardClient] clearErrors error:', error.message);
            throw new Error(`IO Board clear errors failed: ${error.message}`);
        }
    }

    /**
     * 제품 정보 조회
     * @returns {Promise<{product_id: string, sw_version: string}>}
     */
    async getProductInfo() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/product_info`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[IOBoardClient] getProductInfo error:', error.message);
            throw new Error(`IO Board product info query failed: ${error.message}`);
        }
    }

    /**
     * 시스템 리부팅
     */
    async reboot() {
        try {
            await axios.post(
                `${this.baseUrl}/reboot`,
                {},
                { timeout: this.timeout }
            );
            return { success: true };
        } catch (error) {
            console.error('[IOBoardClient] reboot error:', error.message);
            throw new Error(`IO Board reboot failed: ${error.message}`);
        }
    }

    /**
     * 헬스 체크 (연결 상태 확인)
     * @returns {Promise<boolean>}
     */
    async isHealthy() {
        try {
            await axios.get(
                `${this.baseUrl}/status`,
                { timeout: 2000 }
            );
            return true;
        } catch (error) {
            return false;
        }
    }

    // ========================================
    // Recording API (로드셀 데이터 녹화)
    // ========================================

    /**
     * 로드셀 녹화 시작
     *
     * 무게 변화 감지 시작 시점에 호출하여 로드셀 데이터를 수집합니다.
     * 수집된 데이터는 Model 서비스에서 baseline/current 자동 계산에 사용됩니다.
     *
     * @returns {Promise<{status: string, message: string}>}
     */
    async startRecording() {
        try {
            const response = await axios.post(
                `${this.baseUrl}/recording/start`,
                {},
                { timeout: this.timeout }
            );
            console.log('[IOBoardClient] Recording started');
            return response.data;
        } catch (error) {
            console.error('[IOBoardClient] startRecording error:', error.message);
            throw new Error(`IO Board start recording failed: ${error.message}`);
        }
    }

    /**
     * 로드셀 녹화 중지
     *
     * 무게 변화가 안정화된 후 호출하여 녹화를 중지합니다.
     *
     * @returns {Promise<{status: string, message: string}>}
     */
    async stopRecording() {
        try {
            const response = await axios.post(
                `${this.baseUrl}/recording/stop`,
                {},
                { timeout: this.timeout }
            );
            console.log('[IOBoardClient] Recording stopped');
            return response.data;
        } catch (error) {
            console.error('[IOBoardClient] stopRecording error:', error.message);
            throw new Error(`IO Board stop recording failed: ${error.message}`);
        }
    }

    /**
     * 녹화된 로드셀 데이터 조회
     *
     * 녹화 중지 후 호출하여 수집된 데이터를 가져옵니다.
     * 반환 형식은 Model 서비스의 recording 형식과 호환됩니다.
     *
     * @returns {Promise<{logs: Array<{loadcells: string[], timestamp: string}>}>}
     *
     * @example
     * const data = await ioBoardClient.getRecordingData();
     * // data.logs = [
     * //   { loadcells: ["+01000", "+01100", ...], timestamp: "2026-01-29T14:30:00Z" },
     * //   { loadcells: ["+00500", "+00600", ...], timestamp: "2026-01-29T14:30:01Z" },
     * //   ...
     * // ]
     */
    async getRecordingData() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/recording/data`,
                { timeout: this.timeout }
            );
            console.log(`[IOBoardClient] Recording data retrieved: ${response.data.logs?.length || 0} samples`);
            return response.data;
        } catch (error) {
            console.error('[IOBoardClient] getRecordingData error:', error.message);
            throw new Error(`IO Board get recording data failed: ${error.message}`);
        }
    }

    /**
     * 녹화 상태 확인
     *
     * @returns {Promise<{is_recording: boolean, sample_count: number}>}
     */
    async getRecordingStatus() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/recording/status`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            // recording/status 엔드포인트가 없을 수 있음 (이전 버전)
            console.warn('[IOBoardClient] getRecordingStatus not available:', error.message);
            return { is_recording: false, sample_count: 0 };
        }
    }

    /**
     * 녹화 시작 → 중지 → 데이터 조회 통합 API
     *
     * 지정된 시간 동안 녹화를 수행하고 데이터를 반환합니다.
     *
     * @param {number} durationMs - 녹화 시간 (밀리초, 기본 3000ms)
     * @returns {Promise<{logs: Array}>}
     */
    async recordForDuration(durationMs = 3000) {
        try {
            // 1. 녹화 시작
            await this.startRecording();

            // 2. 지정 시간 대기
            await new Promise(resolve => setTimeout(resolve, durationMs));

            // 3. 녹화 중지
            await this.stopRecording();

            // 4. 데이터 조회
            const data = await this.getRecordingData();

            console.log(`[IOBoardClient] Recorded for ${durationMs}ms: ${data.logs?.length || 0} samples`);
            return data;
        } catch (error) {
            console.error('[IOBoardClient] recordForDuration error:', error.message);
            throw new Error(`IO Board record for duration failed: ${error.message}`);
        }
    }
}

module.exports = new IOBoardClient();
