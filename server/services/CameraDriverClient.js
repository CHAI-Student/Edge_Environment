/**
 * CameraDriverClient - Camera Driver 서비스 HTTP 클라이언트
 *
 * Camera Driver FastAPI 서버(port 8003)와 통신하여
 * Zone 카메라 활성화/비활성화, 상태 조회, 캡처 등을 수행합니다.
 */

const axios = require('axios');
const config = require('../config/key');

class CameraDriverClient {
    constructor() {
        this.baseUrl = config.cameraDriverUrl || 'http://localhost:8003';
        this.timeout = 5000; // 5초 타임아웃
    }

    /**
     * Zone 카메라 활성화
     * @param {number} zoneId - Zone ID (0-4)
     * @returns {Promise<{success: boolean, zone_id: number, camera_id: number}>}
     */
    async activateZone(zoneId) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/zone/${zoneId}/activate`,
                {},
                { timeout: this.timeout }
            );
            console.log(`[CameraDriverClient] Zone ${zoneId} activated`);
            return response.data;
        } catch (error) {
            console.error(`[CameraDriverClient] activateZone(${zoneId}) error:`, error.message);
            throw new Error(`Camera zone ${zoneId} activation failed: ${error.message}`);
        }
    }

    /**
     * Zone 카메라 비활성화
     * @param {number} zoneId - Zone ID (0-4)
     * @returns {Promise<{success: boolean, zone_id: number, camera_id: number}>}
     */
    async deactivateZone(zoneId) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/zone/${zoneId}/deactivate`,
                {},
                { timeout: this.timeout }
            );
            console.log(`[CameraDriverClient] Zone ${zoneId} deactivated`);
            return response.data;
        } catch (error) {
            console.error(`[CameraDriverClient] deactivateZone(${zoneId}) error:`, error.message);
            throw new Error(`Camera zone ${zoneId} deactivation failed: ${error.message}`);
        }
    }

    /**
     * 카메라 전체 상태 조회
     * @returns {Promise<{initialized: boolean, streaming: boolean, cameras: Array}>}
     */
    async getStatus() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/status`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[CameraDriverClient] getStatus error:', error.message);
            throw new Error(`Camera status query failed: ${error.message}`);
        }
    }

    /**
     * Zone 프레임 캡처 (스냅샷)
     * @param {number} zoneId - Zone ID (0-4)
     * @param {boolean} includeTop - Top 카메라 포함 여부
     * @returns {Promise<{zone_frame: string|null, top_frame: string|null}>}
     */
    async captureZone(zoneId, includeTop = true) {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/zone/${zoneId}/capture`,
                {
                    params: { include_top: includeTop },
                    timeout: this.timeout
                }
            );
            return response.data;
        } catch (error) {
            console.error(`[CameraDriverClient] captureZone(${zoneId}) error:`, error.message);
            throw new Error(`Zone ${zoneId} capture failed: ${error.message}`);
        }
    }

    /**
     * 특정 카메라 프레임 가져오기 (Base64)
     * @param {number} cameraId - Camera ID (0-5)
     * @returns {Promise<{camera_id: number, frame: string, timestamp: number}>}
     */
    async getFrame(cameraId) {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/camera/${cameraId}/frame`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error(`[CameraDriverClient] getFrame(${cameraId}) error:`, error.message);
            throw new Error(`Camera ${cameraId} frame capture failed: ${error.message}`);
        }
    }

    /**
     * 디바이스 스캔 (사용 가능한 카메라 목록)
     * @returns {Promise<Array<{index: number, name: string, identifier: string, available: boolean}>>}
     */
    async scanDevices() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/devices/scan`,
                { timeout: 10000 } // 스캔은 시간이 더 걸릴 수 있음
            );
            return response.data;
        } catch (error) {
            console.error('[CameraDriverClient] scanDevices error:', error.message);
            throw new Error(`Device scan failed: ${error.message}`);
        }
    }

    /**
     * 헬스 체크 (연결 상태 확인)
     * @returns {Promise<boolean>}
     */
    async isHealthy() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/health`,
                { timeout: 2000 }
            );
            return response.data.status === 'healthy';
        } catch (error) {
            return false;
        }
    }

    /**
     * 상세 상태 조회 (디바이스 정보 포함)
     * @returns {Promise<Object>}
     */
    async getDetailedStatus() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/status/detailed`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[CameraDriverClient] getDetailedStatus error:', error.message);
            throw new Error(`Detailed status query failed: ${error.message}`);
        }
    }

    /**
     * 녹화 시작
     * @param {number} zoneId - Zone ID
     * @param {boolean} includeTop - Top 카메라 포함
     * @returns {Promise<{session_id: string}>}
     */
    async startRecording(zoneId, includeTop = true) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/recording/start`,
                { zone_id: zoneId, include_top: includeTop },
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error(`[CameraDriverClient] startRecording error:`, error.message);
            throw new Error(`Start recording failed: ${error.message}`);
        }
    }

    /**
     * 녹화 종료
     * @returns {Promise<{session_id: string, paths: Object}>}
     */
    async stopRecording() {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/recording/stop`,
                {},
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error(`[CameraDriverClient] stopRecording error:`, error.message);
            throw new Error(`Stop recording failed: ${error.message}`);
        }
    }
}

module.exports = new CameraDriverClient();
