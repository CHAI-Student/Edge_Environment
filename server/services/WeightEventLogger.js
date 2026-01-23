/**
 * WeightEventLogger - 무게 이벤트 로거
 *
 * 로드셀 무게 변화 이벤트를 MongoDB에 저장합니다.
 */

const mongoose = require('mongoose');

// MongoDB 스키마 정의
const weightEventSchema = new mongoose.Schema({
    zone_id: { type: Number, required: true, index: true },
    delta: { type: Number, required: true },
    current_weights: [Number],
    previous_weights: [Number],
    baseline_weights: [Number],
    camera_activated: { type: Boolean, default: false },
    timestamp: { type: Date, default: Date.now, index: true },
    metadata: mongoose.Schema.Types.Mixed
}, {
    collection: 'weight_events',
    timestamps: { createdAt: 'created_at', updatedAt: 'updated_at' }
});

// 인덱스 설정
weightEventSchema.index({ zone_id: 1, timestamp: -1 });
weightEventSchema.index({ timestamp: -1 });

let WeightEvent;

class WeightEventLogger {
    constructor() {
        this.initialized = false;
        this._initModel();
    }

    /**
     * MongoDB 모델 초기화
     */
    _initModel() {
        // 모델이 이미 존재하면 재사용
        if (mongoose.models.WeightEvent) {
            WeightEvent = mongoose.models.WeightEvent;
        } else {
            WeightEvent = mongoose.model('WeightEvent', weightEventSchema);
        }
        this.initialized = true;
    }

    /**
     * 무게 변화 이벤트 저장
     * @param {Object} event - 이벤트 데이터
     * @param {number} event.zone_id - Zone ID
     * @param {number} event.delta - 무게 변화량 (g)
     * @param {number[]} event.current - 현재 무게 배열
     * @param {number[]} event.previous - 이전 무게 배열
     * @param {number[]} [event.baseline] - 베이스라인 무게 배열
     * @param {string} event.timestamp - 타임스탬프
     * @param {boolean} [event.cameras_activated] - 카메라 활성화 여부
     * @returns {Promise<Object>} 저장된 문서
     */
    async logWeightChange(event) {
        try {
            if (mongoose.connection.readyState !== 1) {
                console.warn('[WeightEventLogger] MongoDB not connected, skipping log');
                return null;
            }

            const doc = new WeightEvent({
                zone_id: event.zone_id,
                delta: event.delta,
                current_weights: event.current,
                previous_weights: event.previous,
                baseline_weights: event.baseline,
                camera_activated: event.cameras_activated || false,
                timestamp: event.timestamp ? new Date(event.timestamp) : new Date(),
                metadata: event.metadata
            });

            const saved = await doc.save();
            console.log(`[WeightEventLogger] Logged: Zone ${event.zone_id}, Delta ${event.delta}g`);
            return saved;
        } catch (error) {
            console.error('[WeightEventLogger] Failed to log event:', error.message);
            throw error;
        }
    }

    /**
     * 최근 이벤트 조회
     * @param {Object} options - 조회 옵션
     * @param {number} [options.zone_id] - Zone ID 필터
     * @param {number} [options.limit=50] - 최대 결과 수
     * @param {Date|string} [options.since] - 시작 시간
     * @param {Date|string} [options.until] - 종료 시간
     * @returns {Promise<Array>} 이벤트 배열
     */
    async getRecentEvents(options = {}) {
        try {
            if (mongoose.connection.readyState !== 1) {
                console.warn('[WeightEventLogger] MongoDB not connected');
                return [];
            }

            const query = {};

            if (options.zone_id !== undefined) {
                query.zone_id = options.zone_id;
            }

            if (options.since || options.until) {
                query.timestamp = {};
                if (options.since) {
                    query.timestamp.$gte = new Date(options.since);
                }
                if (options.until) {
                    query.timestamp.$lte = new Date(options.until);
                }
            }

            const limit = options.limit || 50;

            const events = await WeightEvent.find(query)
                .sort({ timestamp: -1 })
                .limit(limit)
                .lean();

            return events;
        } catch (error) {
            console.error('[WeightEventLogger] Failed to get events:', error.message);
            throw error;
        }
    }

    /**
     * Zone별 이벤트 통계 조회
     * @param {number} zoneId - Zone ID
     * @param {number} [hours=24] - 조회할 시간 범위 (시간)
     * @returns {Promise<Object>} 통계 정보
     */
    async getZoneStats(zoneId, hours = 24) {
        try {
            if (mongoose.connection.readyState !== 1) {
                return null;
            }

            const since = new Date(Date.now() - hours * 60 * 60 * 1000);

            const stats = await WeightEvent.aggregate([
                {
                    $match: {
                        zone_id: zoneId,
                        timestamp: { $gte: since }
                    }
                },
                {
                    $group: {
                        _id: '$zone_id',
                        total_events: { $sum: 1 },
                        total_delta: { $sum: '$delta' },
                        avg_delta: { $avg: '$delta' },
                        min_delta: { $min: '$delta' },
                        max_delta: { $max: '$delta' },
                        first_event: { $min: '$timestamp' },
                        last_event: { $max: '$timestamp' }
                    }
                }
            ]);

            return stats.length > 0 ? stats[0] : null;
        } catch (error) {
            console.error('[WeightEventLogger] Failed to get zone stats:', error.message);
            throw error;
        }
    }

    /**
     * 전체 통계 조회
     * @param {number} [hours=24] - 조회할 시간 범위 (시간)
     * @returns {Promise<Object>} 통계 정보
     */
    async getOverallStats(hours = 24) {
        try {
            if (mongoose.connection.readyState !== 1) {
                return null;
            }

            const since = new Date(Date.now() - hours * 60 * 60 * 1000);

            const stats = await WeightEvent.aggregate([
                {
                    $match: {
                        timestamp: { $gte: since }
                    }
                },
                {
                    $group: {
                        _id: null,
                        total_events: { $sum: 1 },
                        total_delta: { $sum: '$delta' },
                        zones_active: { $addToSet: '$zone_id' },
                        first_event: { $min: '$timestamp' },
                        last_event: { $max: '$timestamp' }
                    }
                },
                {
                    $project: {
                        _id: 0,
                        total_events: 1,
                        total_delta: 1,
                        zones_active_count: { $size: '$zones_active' },
                        zones_active: 1,
                        first_event: 1,
                        last_event: 1,
                        hours_covered: { $literal: hours }
                    }
                }
            ]);

            return stats.length > 0 ? stats[0] : {
                total_events: 0,
                total_delta: 0,
                zones_active_count: 0,
                zones_active: [],
                hours_covered: hours
            };
        } catch (error) {
            console.error('[WeightEventLogger] Failed to get overall stats:', error.message);
            throw error;
        }
    }

    /**
     * 오래된 이벤트 삭제 (정리)
     * @param {number} [days=30] - 보관 기간 (일)
     * @returns {Promise<number>} 삭제된 문서 수
     */
    async cleanupOldEvents(days = 30) {
        try {
            if (mongoose.connection.readyState !== 1) {
                return 0;
            }

            const cutoff = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

            const result = await WeightEvent.deleteMany({
                timestamp: { $lt: cutoff }
            });

            console.log(`[WeightEventLogger] Cleaned up ${result.deletedCount} events older than ${days} days`);
            return result.deletedCount;
        } catch (error) {
            console.error('[WeightEventLogger] Cleanup failed:', error.message);
            throw error;
        }
    }
}

module.exports = new WeightEventLogger();
