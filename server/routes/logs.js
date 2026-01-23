/**
 * Logs Routes
 *
 * 로그 조회 API (무게/카메라/시스템/판단)
 */

const express = require('express');
const router = express.Router();
const path = require('path');
const fs = require('fs').promises;
const scheduledLogger = require('../services/ScheduledLogger');

/**
 * 무게 로그 조회
 * GET /api/logs/weight
 *
 * Query:
 * - limit: 최대 결과 수 (default: 50)
 * - date: 특정 날짜 (YYYY-MM-DD)
 */
router.get('/weight', async (req, res) => {
    try {
        const limit = parseInt(req.query.limit) || 50;
        const date = req.query.date;

        let logs;
        if (date) {
            logs = await scheduledLogger.getLogFile('weight', date);
            logs = logs.slice(-limit).reverse();
        } else {
            logs = scheduledLogger.getRecentWeightLogs(limit);
        }

        res.json({
            success: true,
            count: logs.length,
            logs
        });
    } catch (error) {
        console.error('[Logs Route] Get weight logs error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 시스템 로그 조회
 * GET /api/logs/system
 *
 * Query:
 * - limit: 최대 결과 수 (default: 50)
 * - date: 특정 날짜 (YYYY-MM-DD)
 */
router.get('/system', async (req, res) => {
    try {
        const limit = parseInt(req.query.limit) || 50;
        const date = req.query.date;

        let logs;
        if (date) {
            logs = await scheduledLogger.getLogFile('system', date);
            logs = logs.slice(-limit).reverse();
        } else {
            logs = scheduledLogger.getRecentSystemLogs(limit);
        }

        res.json({
            success: true,
            count: logs.length,
            logs
        });
    } catch (error) {
        console.error('[Logs Route] Get system logs error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 판단 로그 조회
 * GET /api/logs/judgment
 *
 * Query:
 * - limit: 최대 결과 수 (default: 50)
 * - date: 특정 날짜 (YYYY-MM-DD)
 */
router.get('/judgment', async (req, res) => {
    try {
        const limit = parseInt(req.query.limit) || 50;
        const date = req.query.date;

        let logs;
        if (date) {
            logs = await scheduledLogger.getLogFile('judgment', date);
            logs = logs.slice(-limit).reverse();
        } else {
            logs = scheduledLogger.getRecentJudgmentLogs(limit);
        }

        res.json({
            success: true,
            count: logs.length,
            logs
        });
    } catch (error) {
        console.error('[Logs Route] Get judgment logs error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 카메라 스냅샷 목록 조회
 * GET /api/logs/camera/:date
 *
 * Params:
 * - date: 날짜 (YYYY-MM-DD)
 */
router.get('/camera/:date', async (req, res) => {
    try {
        const { date } = req.params;

        // 날짜 형식 검증
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
            return res.status(400).json({
                success: false,
                error: 'Invalid date format. Use YYYY-MM-DD.'
            });
        }

        const snapshots = await scheduledLogger.getCameraSnapshots(date);

        res.json({
            success: true,
            date,
            count: snapshots.length,
            snapshots
        });
    } catch (error) {
        console.error('[Logs Route] Get camera snapshots error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 특정 카메라 스냅샷 이미지 제공
 * GET /api/logs/camera/:date/:time/:filename
 */
router.get('/camera/:date/:time/:filename', async (req, res) => {
    try {
        const { date, time, filename } = req.params;

        // 보안: 경로 탐색 방지
        if (filename.includes('..') || time.includes('..')) {
            return res.status(400).json({
                success: false,
                error: 'Invalid path'
            });
        }

        const filepath = path.join(process.cwd(), 'logs', 'camera', date, time, filename);

        try {
            await fs.access(filepath);
            res.sendFile(filepath);
        } catch (error) {
            res.status(404).json({
                success: false,
                error: 'File not found'
            });
        }
    } catch (error) {
        console.error('[Logs Route] Get camera image error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 로그 통계
 * GET /api/logs/stats
 */
router.get('/stats', async (req, res) => {
    try {
        const today = new Date().toISOString().split('T')[0];

        const [weightLogs, systemLogs, judgmentLogs, cameraSnapshots] = await Promise.all([
            scheduledLogger.getLogFile('weight', today).catch(() => []),
            scheduledLogger.getLogFile('system', today).catch(() => []),
            scheduledLogger.getLogFile('judgment', today).catch(() => []),
            scheduledLogger.getCameraSnapshots(today).catch(() => [])
        ]);

        res.json({
            success: true,
            date: today,
            stats: {
                weight_events: weightLogs.length,
                system_logs: systemLogs.length,
                judgments: judgmentLogs.length,
                camera_snapshots: cameraSnapshots.reduce((acc, s) => acc + s.files.length, 0)
            },
            recent: {
                weight: scheduledLogger.getRecentWeightLogs(5),
                system: scheduledLogger.getRecentSystemLogs(1),
                judgment: scheduledLogger.getRecentJudgmentLogs(5)
            }
        });
    } catch (error) {
        console.error('[Logs Route] Get stats error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 사용 가능한 로그 날짜 목록
 * GET /api/logs/dates/:type
 */
router.get('/dates/:type', async (req, res) => {
    try {
        const { type } = req.params;
        const validTypes = ['weight', 'system', 'judgment', 'camera'];

        if (!validTypes.includes(type)) {
            return res.status(400).json({
                success: false,
                error: `Invalid log type. Valid types: ${validTypes.join(', ')}`
            });
        }

        const logsDir = path.join(process.cwd(), 'logs', type);

        try {
            const entries = await fs.readdir(logsDir);
            const dates = entries
                .filter(entry => {
                    if (type === 'camera') {
                        return /^\d{4}-\d{2}-\d{2}$/.test(entry);
                    }
                    return entry.endsWith('.jsonl');
                })
                .map(entry => entry.replace('.jsonl', ''))
                .sort()
                .reverse();

            res.json({
                success: true,
                type,
                dates
            });
        } catch (error) {
            if (error.code === 'ENOENT') {
                return res.json({
                    success: true,
                    type,
                    dates: []
                });
            }
            throw error;
        }
    } catch (error) {
        console.error('[Logs Route] Get dates error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

module.exports = router;
