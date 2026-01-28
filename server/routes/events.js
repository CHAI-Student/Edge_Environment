/**
 * Events Routes
 *
 * 무게 이벤트 조회 및 SSE 스트림 엔드포인트
 */

const express = require('express');
const router = express.Router();
const weightEventLogger = require('../services/WeightEventLogger');
const ioBoardSSE = require('../services/IOBoardSSESubscriber');
const configManager = require('../services/ConfigManager');

// SSE 클라이언트 관리
const sseClients = new Set();

/**
 * SSE 이벤트 스트림
 * GET /sse/events
 *
 * 실시간 무게 변화 이벤트를 클라이언트에 스트리밍합니다.
 */
router.get('/events', (req, res) => {
    // SSE 헤더 설정
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('Access-Control-Allow-Origin', '*');

    // 연결 확인
    res.write('event: connected\n');
    res.write(`data: ${JSON.stringify({ timestamp: new Date().toISOString() })}\n\n`);

    // 클라이언트 등록
    sseClients.add(res);
    console.log(`[SSE] Client connected. Total: ${sseClients.size}`);

    // 연결 종료 처리
    req.on('close', () => {
        sseClients.delete(res);
        console.log(`[SSE] Client disconnected. Total: ${sseClients.size}`);
    });
});

/**
 * SSE 클라이언트들에게 이벤트 브로드캐스트
 * @param {string} eventType - 이벤트 타입
 * @param {Object} data - 이벤트 데이터
 */
function broadcastEvent(eventType, data) {
    const message = `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`;

    for (const client of sseClients) {
        try {
            client.write(message);
        } catch (error) {
            sseClients.delete(client);
        }
    }
}

// IO Board SSE 이벤트 구독 및 브로드캐스트
ioBoardSSE.on('weight_change', async (event) => {
    // SSE 클라이언트에 브로드캐스트
    broadcastEvent('weight_change', event);

    // 이벤트 로그 저장
    try {
        await weightEventLogger.logWeightChange(event);
    } catch (error) {
        console.error('[Events] Failed to log weight event:', error.message);
    }
});

ioBoardSSE.on('loadcell_update', (event) => {
    broadcastEvent('loadcell_update', event);
});

ioBoardSSE.on('connected', () => {
    broadcastEvent('io_board_connected', { timestamp: new Date().toISOString() });
});

ioBoardSSE.on('disconnected', () => {
    broadcastEvent('io_board_disconnected', { timestamp: new Date().toISOString() });
});

ioBoardSSE.on('error', (error) => {
    broadcastEvent('io_board_error', {
        error: error.message,
        timestamp: new Date().toISOString()
    });
});

// 문 상태 이벤트
ioBoardSSE.on('door_update', (event) => {
    broadcastEvent('door_update', event);
});

ioBoardSSE.on('door_opened', (event) => {
    broadcastEvent('door_opened', event);
});

ioBoardSSE.on('door_closed', (event) => {
    broadcastEvent('door_closed', event);
});

ioBoardSSE.on('deadbolt_changed', (event) => {
    broadcastEvent('deadbolt_changed', event);
});

/**
 * 최근 무게 이벤트 조회
 * GET /api/weight/events
 *
 * Query params:
 * - zone_id: Zone ID 필터 (optional)
 * - limit: 최대 결과 수 (default: 50)
 * - since: 시작 시간 (ISO 8601)
 * - until: 종료 시간 (ISO 8601)
 */
router.get('/weight/events', async (req, res) => {
    try {
        const options = {
            limit: parseInt(req.query.limit) || 50
        };

        if (req.query.zone_id !== undefined) {
            options.zone_id = parseInt(req.query.zone_id);
        }
        if (req.query.since) {
            options.since = req.query.since;
        }
        if (req.query.until) {
            options.until = req.query.until;
        }

        const events = await weightEventLogger.getRecentEvents(options);
        res.json({
            success: true,
            count: events.length,
            events
        });
    } catch (error) {
        console.error('[Events Route] Get events error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Zone별 이벤트 통계
 * GET /api/weight/stats/:zoneId
 *
 * Query params:
 * - hours: 조회 시간 범위 (default: 24)
 */
router.get('/weight/stats/:zoneId', async (req, res) => {
    try {
        const zoneId = parseInt(req.params.zoneId);
        const hours = parseInt(req.query.hours) || 24;

        const configManager = require('../services/ConfigManager');
        if (isNaN(zoneId) || !configManager.isZoneEnabled(zoneId)) {
            const enabledZones = configManager.getEnabledZones();
            return res.status(400).json({
                success: false,
                error: `Invalid zone ID. Enabled zones: ${enabledZones.join(', ')}`
            });
        }

        const stats = await weightEventLogger.getZoneStats(zoneId, hours);
        res.json({
            success: true,
            zone_id: zoneId,
            hours,
            stats
        });
    } catch (error) {
        console.error('[Events Route] Get zone stats error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 전체 이벤트 통계
 * GET /api/weight/stats
 *
 * Query params:
 * - hours: 조회 시간 범위 (default: 24)
 */
router.get('/weight/stats', async (req, res) => {
    try {
        const hours = parseInt(req.query.hours) || 24;
        const stats = await weightEventLogger.getOverallStats(hours);
        res.json({
            success: true,
            hours,
            stats
        });
    } catch (error) {
        console.error('[Events Route] Get overall stats error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * IO Board SSE 구독자 상태 조회
 * GET /api/weight/subscriber/status
 */
router.get('/weight/subscriber/status', (req, res) => {
    res.json({
        success: true,
        ...ioBoardSSE.getStatus(),
        sse_clients: sseClients.size
    });
});

/**
 * 베이스라인 무게 리셋
 * POST /api/weight/baseline/reset
 */
router.post('/weight/baseline/reset', (req, res) => {
    ioBoardSSE.resetBaseline();
    res.json({
        success: true,
        message: 'Baseline reset',
        baseline: ioBoardSSE.getStatus().baselineWeights
    });
});

/**
 * 설정 조회
 * GET /api/config
 */
router.get('/config', (req, res) => {
    res.json({
        success: true,
        ...configManager.getAllConfigs()
    });
});

/**
 * Zone 매핑 설정 조회
 * GET /api/config/zone-mapping
 */
router.get('/config/zone-mapping', (req, res) => {
    res.json({
        success: true,
        mapping: configManager.getZoneMapping()
    });
});

/**
 * Zone 매핑 설정 업데이트
 * PUT /api/config/zone-mapping
 */
router.put('/config/zone-mapping', (req, res) => {
    try {
        const result = configManager.updateZoneMapping(req.body);
        if (result) {
            res.json({
                success: true,
                message: 'Zone mapping updated',
                mapping: configManager.getZoneMapping()
            });
        } else {
            res.status(400).json({
                success: false,
                error: 'Failed to update zone mapping'
            });
        }
    } catch (error) {
        console.error('[Events Route] Update zone mapping error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 카메라 디바이스 매핑 조회
 * GET /api/config/camera-device-map
 */
router.get('/config/camera-device-map', (req, res) => {
    res.json({
        success: true,
        mapping: configManager.getCameraDeviceMap()
    });
});

/**
 * 카메라 디바이스 매핑 업데이트
 * PUT /api/config/camera-device-map
 */
router.put('/config/camera-device-map', (req, res) => {
    try {
        const result = configManager.updateCameraDeviceMap(req.body);
        if (result) {
            res.json({
                success: true,
                message: 'Camera device map updated',
                mapping: configManager.getCameraDeviceMap()
            });
        } else {
            res.status(400).json({
                success: false,
                error: 'Failed to update camera device map'
            });
        }
    } catch (error) {
        console.error('[Events Route] Update camera device map error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 설정 다시 로드
 * POST /api/config/reload
 */
router.post('/config/reload', (req, res) => {
    configManager.reload();
    res.json({
        success: true,
        message: 'Configuration reloaded',
        ...configManager.getAllConfigs()
    });
});

module.exports = {
    router,
    broadcastEvent,
    sseClients
};
