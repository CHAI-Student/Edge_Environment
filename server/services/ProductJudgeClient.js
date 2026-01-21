/**
 * ProductJudgeClient - Python product_judge 서비스 HTTP 클라이언트
 *
 * Product Judge FastAPI 서버(port 8002)와 통신하여
 * 상품 판단, 테스트, 시뮬레이션 등을 수행합니다.
 *
 * API Endpoints:
 * - GET /api/health: 헬스 체크
 * - GET /api/products: 등록된 상품 목록
 * - POST /api/judge: 실제 상품 판단 (스냅샷 + 로드셀)
 * - POST /api/test: 테스트용 판단 (YOLO 결과 직접 입력)
 * - POST /api/simulate: 시뮬레이션 (product_id + count 직접 지정)
 * - POST /api/judge/multi-zone: 다중 Zone 동시 판단
 * - POST /api/judge/with-history: 이력 기반 판단 (반납 감지)
 */

const axios = require('axios');
const config = require('../config/key');

class ProductJudgeClient {
    constructor() {
        this.baseUrl = config.productJudgeUrl || 'http://localhost:8002';
        this.timeout = 10000; // 10초 타임아웃 (Vision 처리 고려)
    }

    /**
     * 헬스 체크
     * @returns {Promise<{status: string, version: string, product_count: number}>}
     */
    async healthCheck() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/health`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] healthCheck error:', error.message);
            throw new Error(`Product Judge health check failed: ${error.message}`);
        }
    }

    /**
     * 등록된 상품 목록 조회
     * @returns {Promise<{count: number, products: Array}>}
     */
    async getProducts() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/products`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] getProducts error:', error.message);
            throw new Error(`Product list query failed: ${error.message}`);
        }
    }

    /**
     * 특정 상품 정보 조회
     * @param {number} productId
     * @returns {Promise<Object>}
     */
    async getProduct(productId) {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/products/${productId}`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] getProduct error:', error.message);
            throw new Error(`Product query failed: ${error.message}`);
        }
    }

    /**
     * 테스트용 상품 판단 (YOLO 결과 직접 입력)
     *
     * @param {Object} params
     * @param {Array} params.detections - YOLO 감지 결과 배열
     *   [{xyxy: [x1,y1,x2,y2], conf: 0.8, cls: 26, name: "product_name"}, ...]
     * @param {number} params.delta_weight - 무게 변화량 (음수: 취출)
     * @param {boolean} [params.use_hand_filter=true] - 손 근접 필터 사용 여부
     * @returns {Promise<JudgeResponse>}
     */
    async testJudge(params) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/test`,
                {
                    detections: params.detections,
                    delta_weight: params.delta_weight,
                    use_hand_filter: params.use_hand_filter ?? true,
                },
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] testJudge error:', error.message);
            throw new Error(`Test judge failed: ${error.message}`);
        }
    }

    /**
     * 시뮬레이션 상품 판단 (product_id + count 직접 지정)
     *
     * @param {Object} params
     * @param {number} params.product_id - 상품 ID
     * @param {number} params.count - 수량
     * @param {number} [params.confidence=0.85] - 신뢰도
     * @returns {Promise<JudgeResponse>}
     */
    async simulateJudge(params) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/simulate`,
                {
                    product_id: params.product_id,
                    count: params.count,
                    confidence: params.confidence ?? 0.85,
                },
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] simulateJudge error:', error.message);
            throw new Error(`Simulate judge failed: ${error.message}`);
        }
    }

    /**
     * 실제 상품 판단 (스냅샷 폴더 + 로드셀)
     *
     * @param {Object} params
     * @param {string} params.snapshot_folder - 스냅샷 이미지 폴더 경로
     * @param {number[]} params.loadcell_weights - 현재 로드셀 값 (10채널)
     * @param {number[]} params.baseline_weights - 기준 로드셀 값 (10채널)
     * @param {number} [params.zone_id] - Zone ID (optional)
     * @returns {Promise<JudgeResponse>}
     */
    async judge(params) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/judge`,
                {
                    snapshot_folder: params.snapshot_folder,
                    loadcell_weights: params.loadcell_weights,
                    baseline_weights: params.baseline_weights,
                    zone_id: params.zone_id,
                },
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] judge error:', error.message);
            throw new Error(`Judge failed: ${error.message}`);
        }
    }

    /**
     * 다중 Zone 동시 판단
     *
     * @param {Object} params
     * @param {Array} params.zone_deltas - Zone별 무게 변화 [{zone_id, delta}, ...]
     * @param {Array} params.detections - YOLO 감지 결과
     * @param {number} [params.door_open_duration=0] - 문 열린 시간 (초)
     * @param {boolean} [params.check_cross_zone=true] - Zone 간 이동 체크
     * @returns {Promise<MultiZoneJudgeResponse>}
     */
    async judgeMultiZone(params) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/judge/multi-zone`,
                {
                    zone_deltas: params.zone_deltas,
                    detections: params.detections,
                    door_open_duration: params.door_open_duration ?? 0,
                    check_cross_zone: params.check_cross_zone ?? true,
                },
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] judgeMultiZone error:', error.message);
            throw new Error(`Multi-zone judge failed: ${error.message}`);
        }
    }

    /**
     * 이력 기반 판단 (반납 감지 포함)
     *
     * @param {Object} params
     * @param {Object} params.current_request - 현재 요청
     * @param {Array} params.recent_events - 최근 이벤트 목록
     * @param {boolean} [params.check_return=true] - 반납 체크
     * @returns {Promise<JudgeWithHistoryResponse>}
     */
    async judgeWithHistory(params) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/judge/with-history`,
                {
                    current_request: params.current_request,
                    recent_events: params.recent_events,
                    check_return: params.check_return ?? true,
                },
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] judgeWithHistory error:', error.message);
            throw new Error(`Judge with history failed: ${error.message}`);
        }
    }

    /**
     * 인식률 통계 조회
     * @returns {Promise<RecognitionStats>}
     */
    async getRecognitionStats() {
        try {
            const response = await axios.get(
                `${this.baseUrl}/api/stats/recognition-rate`,
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] getRecognitionStats error:', error.message);
            throw new Error(`Recognition stats query failed: ${error.message}`);
        }
    }

    /**
     * 인식률 통계 초기화
     */
    async resetRecognitionStats() {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/stats/reset`,
                {},
                { timeout: this.timeout }
            );
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] resetRecognitionStats error:', error.message);
            throw new Error(`Reset stats failed: ${error.message}`);
        }
    }

    /**
     * 서비스 연결 상태 확인
     * @returns {Promise<boolean>}
     */
    async isHealthy() {
        try {
            await axios.get(
                `${this.baseUrl}/api/health`,
                { timeout: 2000 }
            );
            return true;
        } catch (error) {
            return false;
        }
    }
}

module.exports = new ProductJudgeClient();
