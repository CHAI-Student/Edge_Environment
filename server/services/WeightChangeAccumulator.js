/**
 * WeightChangeAccumulator - 10초 안정화 타이머 및 이벤트 누적
 *
 * Camera Driver로부터 media-ready 콜백을 받아 이벤트를 누적하고,
 * 10초 동안 추가 이벤트가 없으면 Model 서비스에 판단을 요청합니다.
 *
 * Architecture:
 *     Camera Driver → /api/camera/media-ready → WeightChangeAccumulator
 *                                                      ↓
 *                                              [10초 타이머]
 *                                                      ↓
 *                                              Model Service
 *                                                      ↓
 *                                              PendingItemsStack
 */

const EventEmitter = require('events');
const config = require('../config/key');

class WeightChangeAccumulator extends EventEmitter {
    constructor() {
        super();

        // 안정화 타임아웃 (10초)
        this.stabilityTimeout = parseInt(process.env.WEIGHT_STABILITY_TIMEOUT) || 10000;

        // 누적된 이벤트 (전체 통합 - zone 구분 없이 하나의 타이머)
        this.pendingEvents = [];
        this.stabilityTimer = null;

        // 진행 중인 Model 추론 추적
        this.activeInferenceId = null;
        this.abortController = null;

        // ProductJudgeClient (lazy load)
        this._productJudgeClient = null;

        // PendingItemsStack (lazy load)
        this._pendingItemsStack = null;
    }

    /**
     * ProductJudgeClient 설정
     * @param {Object} client - ProductJudgeClient 인스턴스
     */
    setProductJudgeClient(client) {
        this._productJudgeClient = client;
    }

    /**
     * PendingItemsStack 설정
     * @param {Object} stack - PendingItemsStack 인스턴스
     */
    setPendingItemsStack(stack) {
        this._pendingItemsStack = stack;
    }

    /**
     * 새 이벤트 추가 (media-ready 콜백에서 호출)
     *
     * @param {number} zoneId - Zone ID
     * @param {Object} weightData - 무게 데이터
     * @param {Object} mediaPaths - 미디어 파일 경로
     * @param {string} sessionId - 세션 ID
     */
    async addEvent(zoneId, weightData, mediaPaths, sessionId) {
        const timestamp = Date.now();

        console.log(`[WeightAccumulator] Event received: Zone ${zoneId}, delta=${weightData?.delta_weight}g`);

        // 1. 진행 중인 Model 추론이 있으면 취소
        if (this.activeInferenceId) {
            await this._cancelActiveInference();
        }

        // 2. 기존 타이머 클리어
        if (this.stabilityTimer) {
            clearTimeout(this.stabilityTimer);
            this.stabilityTimer = null;
            console.log(`[WeightAccumulator] Timer reset (new event at Zone ${zoneId})`);
        }

        // 3. 이벤트 데이터 누적
        const eventData = {
            zone_id: zoneId,
            weight_data: weightData,
            media_paths: mediaPaths,
            session_id: sessionId,
            timestamp: timestamp,
        };

        this.pendingEvents.push(eventData);

        console.log(`[WeightAccumulator] Events accumulated: ${this.pendingEvents.length} total`);

        // 4. 새 10초 타이머 시작
        this.stabilityTimer = setTimeout(() => {
            this._onStabilityReached();
        }, this.stabilityTimeout);

        console.log(`[WeightAccumulator] Timer started: ${this.stabilityTimeout}ms`);

        // 이벤트 발생
        this.emit('event_accumulated', {
            zone_id: zoneId,
            pending_count: this.pendingEvents.length,
            timestamp,
        });
    }

    /**
     * 진행 중인 Model 추론 취소
     */
    async _cancelActiveInference() {
        if (!this.activeInferenceId) return;

        console.log(`[WeightAccumulator] Cancelling active inference: ${this.activeInferenceId}`);

        try {
            const client = this._getProductJudgeClient();
            await client.cancelInference(this.activeInferenceId);
            console.log(`[WeightAccumulator] Inference cancelled: ${this.activeInferenceId}`);
        } catch (error) {
            console.error(`[WeightAccumulator] Failed to cancel inference:`, error.message);
        }

        this.activeInferenceId = null;
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    /**
     * 10초 안정화 도달 시 처리
     */
    async _onStabilityReached() {
        console.log(`[WeightAccumulator] Stability reached: processing ${this.pendingEvents.length} events`);

        this.stabilityTimer = null;

        if (this.pendingEvents.length === 0) {
            console.log('[WeightAccumulator] No pending events to process');
            return;
        }

        // 누적된 이벤트 복사 후 초기화
        const eventsToProcess = [...this.pendingEvents];
        this.pendingEvents = [];

        try {
            // 1. 무게 데이터 통합
            const integratedData = this._integrateEvents(eventsToProcess);

            // 2. Model 서비스 호출
            const result = await this._callModelService(integratedData);

            // 3. 결과를 PendingItemsStack에 추가
            if (this._pendingItemsStack && result.success) {
                for (const product of result.products || []) {
                    const item = {
                        timestamp: Date.now() / 1000,
                        zone_id: integratedData.primary_zone_id,
                        action: integratedData.total_delta < 0 ? 'pickup' : 'return',
                        products: [{
                            product_id: product.productId,
                            name: product.name,
                            count: product.count,
                            confidence: product.confidence,
                        }],
                        weight_delta: integratedData.total_delta,
                        media_paths: integratedData.all_media_paths[0] || null,
                    };
                    this._pendingItemsStack.pushItem(item);
                }
            }

            // 이벤트 발생
            this.emit('judgment_complete', {
                events_processed: eventsToProcess.length,
                result: result,
                integrated_data: integratedData,
            });

            console.log(`[WeightAccumulator] Judgment complete: ${result.status}, totalPrice=${result.totalPrice}`);

        } catch (error) {
            console.error('[WeightAccumulator] Processing failed:', error.message);

            this.emit('judgment_error', {
                error: error.message,
                events: eventsToProcess,
            });
        }
    }

    /**
     * 이벤트 통합
     * @param {Array} events - 누적된 이벤트 배열
     * @returns {Object} 통합된 데이터
     */
    _integrateEvents(events) {
        // Zone별 그룹핑
        const zoneGroups = new Map();
        let totalDelta = 0;
        const allMediaPaths = [];

        for (const event of events) {
            const zoneId = event.zone_id;

            if (!zoneGroups.has(zoneId)) {
                zoneGroups.set(zoneId, {
                    zone_id: zoneId,
                    events: [],
                    delta_sum: 0,
                });
            }

            const group = zoneGroups.get(zoneId);
            group.events.push(event);
            group.delta_sum += event.weight_data?.delta_weight || 0;

            totalDelta += event.weight_data?.delta_weight || 0;

            if (event.media_paths) {
                allMediaPaths.push(event.media_paths);
            }
        }

        // 가장 큰 변화가 있는 Zone을 primary로 선택
        let primaryZoneId = 0;
        let maxAbsDelta = 0;

        for (const [zoneId, group] of zoneGroups) {
            if (Math.abs(group.delta_sum) > maxAbsDelta) {
                maxAbsDelta = Math.abs(group.delta_sum);
                primaryZoneId = zoneId;
            }
        }

        // 통합된 weight_data 생성
        const firstEvent = events[0];
        const lastEvent = events[events.length - 1];

        const integratedWeightData = {
            before_weights: firstEvent.weight_data?.before_weights || [],
            after_weights: lastEvent.weight_data?.after_weights || [],
            delta_weight: totalDelta,
            channels: [...new Set(events.flatMap(e => e.weight_data?.channels || []))],
        };

        return {
            primary_zone_id: primaryZoneId,
            zone_groups: Object.fromEntries(zoneGroups),
            total_delta: totalDelta,
            integrated_weight_data: integratedWeightData,
            all_media_paths: allMediaPaths,
            event_count: events.length,
            first_timestamp: firstEvent.timestamp,
            last_timestamp: lastEvent.timestamp,
        };
    }

    /**
     * Model 서비스 호출
     * @param {Object} integratedData - 통합된 데이터
     * @returns {Promise<Object>} 판단 결과
     */
    async _callModelService(integratedData) {
        const client = this._getProductJudgeClient();

        // inference_id 생성 (substr deprecated → slice 사용)
        const inferenceId = `inf_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
        this.activeInferenceId = inferenceId;

        // AbortController 생성
        this.abortController = new AbortController();

        try {
            const requestData = {
                zone_id: integratedData.primary_zone_id,
                weight_data: integratedData.integrated_weight_data,
                media_paths: integratedData.all_media_paths[0] || null,
                timestamp: Date.now() / 1000,
                inference_id: inferenceId,
            };

            console.log(`[WeightAccumulator] Calling Model service: inference_id=${inferenceId}`);

            const result = await client.judgeWithWeightData(requestData, this.abortController.signal);

            return result;

        } catch (error) {
            if (error.name === 'AbortError') {
                console.log(`[WeightAccumulator] Inference aborted: ${inferenceId}`);
                return { success: false, status: 'cancelled', products: [] };
            }

            throw error;
        } finally {
            // 리소스 정리 보장
            this.activeInferenceId = null;
            if (this.abortController) {
                this.abortController = null;
            }
        }
    }

    /**
     * ProductJudgeClient 가져오기
     */
    _getProductJudgeClient() {
        if (!this._productJudgeClient) {
            try {
                this._productJudgeClient = require('./ProductJudgeClient');
            } catch (error) {
                console.error('[WeightAccumulator] Failed to load ProductJudgeClient:', error.message);
                throw new Error('ProductJudgeClient module not available');
            }
        }
        if (!this._productJudgeClient) {
            throw new Error('ProductJudgeClient not initialized');
        }
        return this._productJudgeClient;
    }

    /**
     * 강제 처리 (문 닫힘 시 호출)
     * @returns {Promise<Object>} 처리 결과
     */
    async forceProcess() {
        if (this.stabilityTimer) {
            clearTimeout(this.stabilityTimer);
            this.stabilityTimer = null;
        }

        if (this.pendingEvents.length === 0) {
            return { processed: false, reason: 'no_pending_events' };
        }

        // 이벤트 수를 먼저 캡처 (처리 후 배열이 초기화되므로)
        const eventCount = this.pendingEvents.length;

        console.log(`[WeightAccumulator] Force processing ${eventCount} events`);

        await this._onStabilityReached();

        return { processed: true, event_count: eventCount };
    }

    /**
     * 상태 초기화
     */
    reset() {
        if (this.stabilityTimer) {
            clearTimeout(this.stabilityTimer);
            this.stabilityTimer = null;
        }

        this.pendingEvents = [];
        this.activeInferenceId = null;

        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }

        console.log('[WeightAccumulator] Reset');
    }

    /**
     * 상태 조회
     * @returns {Object} 현재 상태
     */
    getStatus() {
        return {
            pending_events: this.pendingEvents.length,
            pending_zones: [...new Set(this.pendingEvents.map(e => e.zone_id))],
            timer_active: this.stabilityTimer !== null,
            active_inference_id: this.activeInferenceId,
            stability_timeout: this.stabilityTimeout,
        };
    }
}

module.exports = new WeightChangeAccumulator();
