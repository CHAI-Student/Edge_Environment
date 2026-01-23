/**
 * Camera Control Routes
 *
 * Node.js를 통한 카메라 제어 API 엔드포인트
 */

const express = require('express');
const router = express.Router();
const cameraClient = require('../services/CameraDriverClient');
const configManager = require('../services/ConfigManager');

/**
 * Zone 카메라 활성화
 * POST /api/camera/zone/:zoneId/activate
 */
router.post('/zone/:zoneId/activate', async (req, res) => {
    try {
        const zoneId = parseInt(req.params.zoneId);

        if (isNaN(zoneId) || zoneId < 0 || zoneId > 4) {
            return res.status(400).json({
                success: false,
                error: 'Invalid zone ID. Must be 0-4.'
            });
        }

        const result = await cameraClient.activateZone(zoneId);
        res.json({
            success: true,
            zone_id: zoneId,
            camera_id: configManager.getCameraIdForZone(zoneId),
            ...result
        });
    } catch (error) {
        console.error('[Camera Route] Activate zone error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Zone 카메라 비활성화
 * POST /api/camera/zone/:zoneId/deactivate
 */
router.post('/zone/:zoneId/deactivate', async (req, res) => {
    try {
        const zoneId = parseInt(req.params.zoneId);

        if (isNaN(zoneId) || zoneId < 0 || zoneId > 4) {
            return res.status(400).json({
                success: false,
                error: 'Invalid zone ID. Must be 0-4.'
            });
        }

        const result = await cameraClient.deactivateZone(zoneId);
        res.json({
            success: true,
            zone_id: zoneId,
            ...result
        });
    } catch (error) {
        console.error('[Camera Route] Deactivate zone error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 카메라 전체 상태 조회
 * GET /api/camera/status
 */
router.get('/status', async (req, res) => {
    try {
        const status = await cameraClient.getStatus();
        res.json(status);
    } catch (error) {
        console.error('[Camera Route] Get status error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 카메라 상세 상태 조회 (디바이스 정보 포함)
 * GET /api/camera/status/detailed
 */
router.get('/status/detailed', async (req, res) => {
    try {
        const status = await cameraClient.getDetailedStatus();
        res.json(status);
    } catch (error) {
        console.error('[Camera Route] Get detailed status error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Zone 프레임 캡처
 * GET /api/camera/zone/:zoneId/capture
 */
router.get('/zone/:zoneId/capture', async (req, res) => {
    try {
        const zoneId = parseInt(req.params.zoneId);
        const includeTop = req.query.include_top !== 'false';

        if (isNaN(zoneId) || zoneId < 0 || zoneId > 4) {
            return res.status(400).json({
                success: false,
                error: 'Invalid zone ID. Must be 0-4.'
            });
        }

        const result = await cameraClient.captureZone(zoneId, includeTop);
        res.json({
            success: true,
            zone_id: zoneId,
            ...result
        });
    } catch (error) {
        console.error('[Camera Route] Capture zone error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 특정 카메라 프레임 가져오기
 * GET /api/camera/:cameraId/frame
 */
router.get('/:cameraId/frame', async (req, res) => {
    try {
        const cameraId = parseInt(req.params.cameraId);

        if (isNaN(cameraId) || cameraId < 0 || cameraId > 5) {
            return res.status(400).json({
                success: false,
                error: 'Invalid camera ID. Must be 0-5.'
            });
        }

        const result = await cameraClient.getFrame(cameraId);
        res.json({
            success: true,
            ...result
        });
    } catch (error) {
        console.error('[Camera Route] Get frame error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 디바이스 스캔
 * GET /api/camera/devices/scan
 */
router.get('/devices/scan', async (req, res) => {
    try {
        const devices = await cameraClient.scanDevices();
        res.json({
            success: true,
            devices,
            nvidia_mode: configManager.isNvidiaMode()
        });
    } catch (error) {
        console.error('[Camera Route] Scan devices error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 카메라 헬스 체크
 * GET /api/camera/health
 */
router.get('/health', async (req, res) => {
    try {
        const isHealthy = await cameraClient.isHealthy();
        res.json({
            status: isHealthy ? 'healthy' : 'unhealthy',
            service: 'camera_driver',
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        res.status(503).json({
            status: 'unhealthy',
            service: 'camera_driver',
            error: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

/**
 * 녹화 시작
 * POST /api/camera/recording/start
 */
router.post('/recording/start', async (req, res) => {
    try {
        const { zone_id, include_top = true } = req.body;
        const result = await cameraClient.startRecording(zone_id, include_top);
        res.json({
            success: true,
            ...result
        });
    } catch (error) {
        console.error('[Camera Route] Start recording error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 녹화 종료
 * POST /api/camera/recording/stop
 */
router.post('/recording/stop', async (req, res) => {
    try {
        const result = await cameraClient.stopRecording();
        res.json({
            success: true,
            ...result
        });
    } catch (error) {
        console.error('[Camera Route] Stop recording error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

module.exports = router;
