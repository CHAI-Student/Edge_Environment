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
     * 상품 판단 (통합 API)
     *
     * 레거시 형식과 새로운 형식 모두 지원합니다.
     *
     * @param {Object} params
     * @param {number} [params.zone_id] - Zone ID (0-4)
     * @param {boolean} [params.vision_only] - Vision 전용 모드 (로드셀 없이)
     * @param {Object} [params.weight_data] - 무게 데이터
     * @param {Object} [params.media_paths] - 이미지 경로
     * @param {string} [params.snapshot_folder] - 스냅샷 폴더 (레거시)
     * @param {number[]} [params.loadcell_weights] - 현재 로드셀 값 (레거시)
     * @param {number[]} [params.baseline_weights] - 기준 로드셀 값 (레거시)
     * @returns {Promise<JudgeResponse>}
     */
    async judge(params) {
        try {
            // vision_only 또는 media_paths가 있으면 새 형식 사용
            const requestBody = {
                zone_id: params.zone_id,
            };

            // 새 형식 필드
            if (params.vision_only !== undefined) {
                requestBody.vision_only = params.vision_only;
            }
            if (params.media_paths) {
                requestBody.media_paths = params.media_paths;
            }
            if (params.weight_data) {
                requestBody.weight_data = params.weight_data;
            }
            if (params.delta_weight !== undefined) {
                requestBody.delta_weight = params.delta_weight;
            }
            if (params.timestamp) {
                requestBody.timestamp = params.timestamp;
            }
            if (params.inference_id) {
                requestBody.inference_id = params.inference_id;
            }
            if (params.vision_candidates) {
                requestBody.vision_candidates = params.vision_candidates;
            }

            // 레거시 형식 필드
            if (params.snapshot_folder) {
                requestBody.snapshot_folder = params.snapshot_folder;
            }
            if (params.loadcell_weights) {
                requestBody.loadcell_weights = params.loadcell_weights;
            }
            if (params.baseline_weights) {
                requestBody.baseline_weights = params.baseline_weights;
            }

            const response = await axios.post(
                `${this.baseUrl}/api/judge`,
                requestBody,
                { timeout: this.timeout }
            );
            console.log(`[ProductJudgeClient] judge completed: zone=${params.zone_id}, status=${response.data.status}`);
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] judge error:', error.message);
            throw new Error(`Judge failed: ${error.message}`);
        }
    }

    /**
     * 상품 판단 (새로운 형식: 무게 데이터 + 이미지 경로)
     *
     * Node.js 오케스트레이터가 SSE 이벤트와 이미지를 수집하여
     * Model 서비스에 전달하는 새로운 API.
     *
     * @param {Object} params
     * @param {number} params.zone_id - Zone ID (0-4)
     * @param {Object} params.weight_data - 무게 데이터
     * @param {number[]} params.weight_data.before_weights - 변화 전 무게 (10채널)
     * @param {number[]} params.weight_data.after_weights - 변화 후 무게 (10채널)
     * @param {number} params.weight_data.delta_weight - 무게 변화량 (g)
     * @param {number[]} [params.weight_data.channels] - 변화 감지된 채널
     * @param {Object} [params.media_paths] - 이미지 경로
     * @param {string} [params.media_paths.image_folder] - 스냅샷 폴더 경로 (예: data/20260128_115230/images)
     * @param {number[]} [params.media_paths.active_zones] - 활성화할 zone 목록 (예: [0, 1, 2])
     * @param {string} [params.media_paths.top_image] - Top 카메라 이미지
     * @param {string} [params.media_paths.side_image] - Side 카메라 이미지
     * @param {number} params.timestamp - 이벤트 발생 시각 (Unix timestamp)
     * @param {Array} [params.vision_candidates] - 미리 추론한 Vision 후보군
     * @param {string} [params.inference_id] - 추론 ID (취소용)
     * @param {AbortSignal} [abortSignal] - 취소 시그널
     * @returns {Promise<JudgeResponse>}
     */
    async judgeWithWeightData(params, abortSignal = null) {
        try {
            const requestConfig = { timeout: this.timeout };

            // AbortSignal 지원
            if (abortSignal) {
                requestConfig.signal = abortSignal;
            }

            // media_paths 구성 (active_zones 포함)
            let mediaPaths = null;
            if (params.media_paths) {
                mediaPaths = {
                    image_folder: params.media_paths.image_folder || null,
                    active_zones: params.media_paths.active_zones || null,
                    top_image: params.media_paths.top_image || null,
                    side_image: params.media_paths.side_image || null,
                };
            }

            const response = await axios.post(
                `${this.baseUrl}/api/judge`,
                {
                    zone_id: params.zone_id,
                    weight_data: params.weight_data,
                    media_paths: mediaPaths,
                    timestamp: params.timestamp,
                    vision_candidates: params.vision_candidates || null,
                    inference_id: params.inference_id || null,
                },
                requestConfig
            );
            console.log(`[ProductJudgeClient] judgeWithWeightData completed: zone=${params.zone_id}, status=${response.data.status}`);
            return response.data;
        } catch (error) {
            // AbortError 처리
            if (axios.isCancel(error) || error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
                const abortError = new Error('Request aborted');
                abortError.name = 'AbortError';
                throw abortError;
            }
            console.error('[ProductJudgeClient] judgeWithWeightData error:', error.message);
            throw new Error(`Judge with weight data failed: ${error.message}`);
        }
    }

    /**
     * 카메라 전용 상품 판단 (로드셀 없이)
     *
     * 로드셀 연결 없이 카메라만으로 상품을 판단합니다.
     * 무게 검증이 없으므로 개수는 1로 고정되고 신뢰도가 낮아집니다.
     *
     * @param {Object} params
     * @param {number} params.zone_id - Zone ID (0-4)
     * @param {Object} params.media_paths - 이미지 경로
     * @param {string} [params.media_paths.image_folder] - 스냅샷 폴더 경로 (예: data/20260128_115230/images)
     * @param {number[]} [params.media_paths.active_zones] - 활성화할 zone 목록 (예: [0, 1, 2])
     * @param {string} [params.media_paths.top_image] - Top 카메라 이미지
     * @param {string} [params.media_paths.side_image] - Side 카메라 이미지
     * @param {number} [params.timestamp] - 이벤트 발생 시각 (Unix timestamp)
     * @param {string} [params.inference_id] - 추론 ID (취소용)
     * @returns {Promise<JudgeResponse>}
     */
    async judgeWithCameraOnly(params) {
        try {
            // media_paths 구성 (active_zones 포함)
            let mediaPaths = null;
            if (params.media_paths) {
                mediaPaths = {
                    image_folder: params.media_paths.image_folder || null,
                    active_zones: params.media_paths.active_zones || null,
                    top_image: params.media_paths.top_image || null,
                    side_image: params.media_paths.side_image || null,
                };
            }

            const response = await axios.post(
                `${this.baseUrl}/api/judge`,
                {
                    zone_id: params.zone_id,
                    weight_data: null,  // 무게 데이터 없음
                    media_paths: mediaPaths,
                    timestamp: params.timestamp || Date.now() / 1000,
                    vision_candidates: params.vision_candidates || null,
                    inference_id: params.inference_id || null,
                    vision_only: true,  // Vision 전용 모드 명시
                },
                { timeout: this.timeout }
            );
            console.log(`[ProductJudgeClient] judgeWithCameraOnly completed: zone=${params.zone_id}, status=${response.data.status}`);
            return response.data;
        } catch (error) {
            console.error('[ProductJudgeClient] judgeWithCameraOnly error:', error.message);
            throw new Error(`Camera-only judge failed: ${error.message}`);
        }
    }

    /**
     * 진행 중인 추론 취소
     *
     * Model 서비스에서 진행 중인 추론을 중단합니다.
     *
     * @param {string} inferenceId - 추론 ID
     * @returns {Promise<{cancelled: boolean, inference_id: string}>}
     */
    async cancelInference(inferenceId) {
        try {
            const response = await axios.post(
                `${this.baseUrl}/api/judge/cancel`,
                { inference_id: inferenceId },
                { timeout: 5000 }  // 취소는 빠르게
            );
            console.log(`[ProductJudgeClient] Inference cancelled: ${inferenceId}`);
            return response.data;
        } catch (error) {
            // 404는 이미 완료된 추론
            if (error.response && error.response.status === 404) {
                console.log(`[ProductJudgeClient] Inference not found (already completed): ${inferenceId}`);
                return { cancelled: false, inference_id: inferenceId, reason: 'not_found' };
            }
            console.error('[ProductJudgeClient] cancelInference error:', error.message);
            throw new Error(`Cancel inference failed: ${error.message}`);
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

    // ========================================
    // Recording 기반 판단 API
    // ========================================

    /**
     * Recording 데이터로 상품 판단
     *
     * IO Board의 recording 데이터를 직접 전달하면,
     * Model 서비스가 자동으로 baseline/current를 계산하고
     * delta weight를 산출하여 판단합니다.
     *
     * @param {Object} params
     * @param {number} params.zone_id - Zone ID (0-4)
     * @param {Array<{loadcells: string[], timestamp: string}>} params.recording - Recording 데이터
     * @param {Object} [params.media_paths] - 이미지 경로 (선택)
     * @param {string} [params.media_paths.image_folder] - 스냅샷 폴더
     * @param {string} [params.media_paths.top_image] - Top 카메라 이미지
     * @param {string} [params.media_paths.side_image] - Side 카메라 이미지
     * @param {number} [params.timestamp] - 이벤트 발생 시각 (Unix timestamp)
     * @param {string} [params.inference_id] - 추론 ID (취소용)
     * @param {AbortSignal} [abortSignal] - 취소 시그널
     * @returns {Promise<JudgeResponse>}
     *
     * @example
     * // IO Board에서 recording 데이터 가져오기
     * const recordingData = await ioBoardClient.getRecordingData();
     *
     * // Model 서비스에 판단 요청
     * const result = await productJudgeClient.judgeWithRecording({
     *   zone_id: 0,
     *   recording: recordingData.logs,
     *   media_paths: { image_folder: 'data/20260129_143000/images' }
     * });
     */
    async judgeWithRecording(params, abortSignal = null) {
        try {
            const requestConfig = { timeout: this.timeout };

            // AbortSignal 지원
            if (abortSignal) {
                requestConfig.signal = abortSignal;
            }

            // media_paths 구성
            let mediaPaths = null;
            if (params.media_paths) {
                mediaPaths = {
                    image_folder: params.media_paths.image_folder || null,
                    active_zones: params.media_paths.active_zones || null,
                    top_image: params.media_paths.top_image || null,
                    side_image: params.media_paths.side_image || null,
                };
            }

            const requestBody = {
                zone_id: params.zone_id,
                recording: params.recording,  // Recording 형식 사용
                media_paths: mediaPaths,
                timestamp: params.timestamp || Date.now() / 1000,
                inference_id: params.inference_id || null,
            };

            console.log(`[ProductJudgeClient] judgeWithRecording: zone=${params.zone_id}, samples=${params.recording?.length || 0}`);

            const response = await axios.post(
                `${this.baseUrl}/api/judge`,
                requestBody,
                requestConfig
            );

            console.log(`[ProductJudgeClient] judgeWithRecording completed: zone=${params.zone_id}, status=${response.data.status}`);
            return response.data;
        } catch (error) {
            // AbortError 처리
            if (axios.isCancel(error) || error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
                const abortError = new Error('Request aborted');
                abortError.name = 'AbortError';
                throw abortError;
            }
            console.error('[ProductJudgeClient] judgeWithRecording error:', error.message);
            throw new Error(`Judge with recording failed: ${error.message}`);
        }
    }

    /**
     * Recording 데이터 + 카메라 스냅샷으로 상품 판단 (통합 API)
     *
     * IO Board recording 데이터와 Camera Driver 스냅샷을 함께 사용하여
     * 가장 정확한 상품 판단을 수행합니다.
     *
     * @param {Object} params
     * @param {number} params.zone_id - Zone ID (0-4)
     * @param {Array<{loadcells: string[], timestamp: string}>} params.recording - Recording 데이터
     * @param {string} params.snapshot_folder - 스냅샷 저장 폴더
     * @param {boolean} [params.include_top=true] - Top 카메라 포함 여부
     * @param {string} [params.inference_id] - 추론 ID
     * @param {AbortSignal} [abortSignal] - 취소 시그널
     * @returns {Promise<JudgeResponse>}
     */
    async judgeWithRecordingAndSnapshot(params, abortSignal = null) {
        // Zone에 해당하는 Side 카메라 ID (Zone 0 → CAM 1, Zone 1 → CAM 2, ...)
        const sideCameraId = params.zone_id + 1;

        const mediaPaths = {
            image_folder: params.snapshot_folder,
            active_zones: [params.zone_id],
        };

        // 기본 이미지 경로 구성 (Camera Driver 규칙)
        if (params.include_top !== false) {
            mediaPaths.top_image = `${params.snapshot_folder}/cam_0/snapshot.jpg`;
        }
        mediaPaths.side_image = `${params.snapshot_folder}/cam_${sideCameraId}/snapshot.jpg`;

        return this.judgeWithRecording({
            zone_id: params.zone_id,
            recording: params.recording,
            media_paths: mediaPaths,
            inference_id: params.inference_id,
        }, abortSignal);
    }
}

module.exports = new ProductJudgeClient();
