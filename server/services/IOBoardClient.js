/**
 * IOBoardClient - Python io_board 서비스 HTTP 클라이언트
 *
 * IO Board FastAPI 서버(port 8001)와 통신하여
 * 데드볼트 제어, 로드셀 조회 등을 수행합니다.
 */

const axios = require('axios');
const config = require('../config/key');

class IOBoardClient {
    constructor() {
        this.baseUrl = config.ioBoardUrl || 'http://localhost:8001';
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
}

module.exports = new IOBoardClient();
