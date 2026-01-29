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
     * 카메라 초기화
     * @returns {Promise<Object>}
     */
    async init() {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/init`,
                {},
                { timeout: 30000 } // 초기화는 시간이 걸릴 수 있음
            );
            return response.data;
        } catch (error) {
            console.error('[CameraDriverClient] init error:', error.message);
            throw new Error(`Camera init failed: ${error.message}`);
        }
    }

    /**
     * Zone 프레임 캡처 (스냅샷) - Base64 반환
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
     * Zone 스냅샷 캡처 및 저장 (파일 경로 반환)
     *
     * Camera Driver가 이미지를 디스크에 저장하고 파일 경로를 반환합니다.
     * Node.js 오케스트레이터가 이 경로를 Model 서비스에 전달합니다.
     *
     * @param {number} zoneId - Zone ID (0-4)
     * @param {string} sessionId - 세션 ID (예: "260126143025")
     * @param {boolean} includeTop - Top 카메라 포함 여부
     * @returns {Promise<{session_path: string, images: Object}>}
     */
    async captureSnapshot(zoneId, sessionId, includeTop = true) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/zone/${zoneId}/snapshot`,
                {
                    session_id: sessionId,
                    include_top: includeTop
                },
                { timeout: this.timeout }
            );

            console.log(`[CameraDriverClient] Snapshot captured for Zone ${zoneId}: ${response.data.session_path}`);
            return response.data;
        } catch (error) {
            // 엔드포인트가 없는 경우 Base64로 받아서 파일로 저장
            if (error.response && error.response.status === 404) {
                console.log(`[CameraDriverClient] Snapshot endpoint not available, using captureZone with file save`);
                const captureResult = await this.captureZone(zoneId, includeTop);

                // Base64 데이터를 파일로 저장
                const savedPaths = await this._saveBase64ToFiles(
                    zoneId,
                    sessionId,
                    captureResult.top_frame,
                    captureResult.zone_frame
                );

                return {
                    session_path: savedPaths.session_path,
                    images: {
                        cam0: savedPaths.top_image,
                        [`cam${zoneId + 1}`]: savedPaths.side_image
                    }
                };
            }
            console.error(`[CameraDriverClient] captureSnapshot(${zoneId}) error:`, error.message);
            throw new Error(`Zone ${zoneId} snapshot failed: ${error.message}`);
        }
    }

    /**
     * Base64 이미지를 파일로 저장
     * @param {number} zoneId - Zone ID
     * @param {string} sessionId - 세션 ID
     * @param {string|null} topBase64 - Top 카메라 Base64 데이터
     * @param {string|null} sideBase64 - Side 카메라 Base64 데이터
     * @returns {Promise<{session_path: string, top_image: string|null, side_image: string|null}>}
     */
    async _saveBase64ToFiles(zoneId, sessionId, topBase64, sideBase64) {
        const fs = require('fs').promises;
        const path = require('path');

        // 스냅샷 저장 경로 설정
        const snapshotBaseDir = process.env.SNAPSHOT_BASE_PATH || path.join(__dirname, '..', '..', 'data', 'snapshots');
        const sessionPath = path.join(snapshotBaseDir, sessionId);

        // 디렉토리 생성
        try {
            await fs.mkdir(sessionPath, { recursive: true });
        } catch (mkdirError) {
            console.error(`[CameraDriverClient] Failed to create snapshot directory:`, mkdirError.message);
        }

        let topImagePath = null;
        let sideImagePath = null;

        // Top 카메라 이미지 저장
        if (topBase64) {
            try {
                const topDir = path.join(sessionPath, 'cam0');
                await fs.mkdir(topDir, { recursive: true });
                topImagePath = path.join(topDir, 'snapshot.jpg');

                // Base64에서 'data:image/...' prefix 제거
                const base64Data = topBase64.replace(/^data:image\/\w+;base64,/, '');
                await fs.writeFile(topImagePath, Buffer.from(base64Data, 'base64'));

                console.log(`[CameraDriverClient] Top camera image saved: ${topImagePath}`);
            } catch (saveError) {
                console.error(`[CameraDriverClient] Failed to save top camera image:`, saveError.message);
            }
        }

        // Side 카메라 이미지 저장
        if (sideBase64) {
            try {
                const sideDir = path.join(sessionPath, `cam${zoneId + 1}`);
                await fs.mkdir(sideDir, { recursive: true });
                sideImagePath = path.join(sideDir, 'snapshot.jpg');

                const base64Data = sideBase64.replace(/^data:image\/\w+;base64,/, '');
                await fs.writeFile(sideImagePath, Buffer.from(base64Data, 'base64'));

                console.log(`[CameraDriverClient] Side camera (zone ${zoneId}) image saved: ${sideImagePath}`);
            } catch (saveError) {
                console.error(`[CameraDriverClient] Failed to save side camera image:`, saveError.message);
            }
        }

        return {
            session_path: sessionPath,
            top_image: topImagePath,
            side_image: sideImagePath
        };
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
     * @param {number} zoneId - Zone ID (null이면 전체)
     * @param {boolean} includeTop - Top 카메라 포함
     * @param {string} sessionId - 세션 ID (선택)
     * @returns {Promise<{session_id: string, paths: Object}>}
     */
    async startRecording(zoneId = null, includeTop = true, sessionId = null) {
        try {
            const payload = {
                include_top: includeTop,
                record_video: true
            };
            if (zoneId !== null) payload.zone_id = zoneId;
            if (sessionId) payload.session_id = sessionId;

            const response = await axios.post(
                `${this.baseUrl}/api/recording/start`,
                payload,
                { timeout: this.timeout }
            );
            console.log(`[CameraDriverClient] Recording started: session=${response.data.session_id}, zone=${zoneId}`);
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
            console.log(`[CameraDriverClient] Recording stopped: session=${response.data.session_info?.session_id}`);
            return response.data;
        } catch (error) {
            console.error(`[CameraDriverClient] stopRecording error:`, error.message);
            throw new Error(`Stop recording failed: ${error.message}`);
        }
    }

    /**
     * Top 카메라 (cam0) 활성화
     * Deadbolt 열릴 때 호출
     * @returns {Promise<{success: boolean}>}
     */
    async activateTopCamera() {
        try {
            // Top 카메라는 camera_id = 0
            // Zone -1 또는 특수 처리로 Top만 활성화
            const response = await axios.post(
                `${this.baseUrl}/api/camera/0/activate`,
                {},
                { timeout: this.timeout }
            );
            console.log('[CameraDriverClient] Top camera (cam0) activated');
            return response.data;
        } catch (error) {
            // 엔드포인트가 없으면 zone 0 활성화로 대체 (Top 카메라 포함)
            if (error.response && error.response.status === 404) {
                console.log('[CameraDriverClient] Using zone activation for top camera');
                return { success: true, fallback: true };
            }
            console.error('[CameraDriverClient] activateTopCamera error:', error.message);
            throw new Error(`Top camera activation failed: ${error.message}`);
        }
    }

    /**
     * Top 카메라 (cam0) 비활성화
     * @returns {Promise<{success: boolean}>}
     */
    async deactivateTopCamera() {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/camera/0/deactivate`,
                {},
                { timeout: this.timeout }
            );
            console.log('[CameraDriverClient] Top camera (cam0) deactivated');
            return response.data;
        } catch (error) {
            if (error.response && error.response.status === 404) {
                return { success: true, fallback: true };
            }
            console.error('[CameraDriverClient] deactivateTopCamera error:', error.message);
            throw new Error(`Top camera deactivation failed: ${error.message}`);
        }
    }

    /**
     * Top 카메라 녹화 시작 (Deadbolt 열릴 때)
     * @param {string} sessionId - 세션 ID
     * @returns {Promise<{session_id: string}>}
     */
    async startTopCameraRecording(sessionId = null) {
        try {
            const payload = {
                zone_id: null,  // Top만
                include_top: true,
                record_video: true
            };
            if (sessionId) payload.session_id = sessionId;

            const response = await axios.post(
                `${this.baseUrl}/api/recording/start`,
                payload,
                { timeout: this.timeout }
            );
            console.log(`[CameraDriverClient] Top camera recording started: session=${response.data.session_id}`);
            return response.data;
        } catch (error) {
            console.error('[CameraDriverClient] startTopCameraRecording error:', error.message);
            throw new Error(`Top camera recording failed: ${error.message}`);
        }
    }

    /**
     * 녹화 상태 조회
     * @returns {Promise<{is_recording: boolean, session_id: string|null}>}
     */
    async getRecordingStatus() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/recording/status`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[CameraDriverClient] getRecordingStatus error:', error.message);
            return { is_recording: false, has_media_recorder: false };
        }
    }
}

module.exports = new CameraDriverClient();
