/**
 * IO Board Routes
 *
 * Python IO Board 서비스(port 8001) 프록시 라우트
 */

const express = require('express');
const router = express.Router();
const ioBoardClient = require('../services/IOBoardClient');

/**
 * 로드셀 값 조회
 * GET /api/io-board/loadcells
 */
router.get('/loadcells', async (req, res) => {
    try {
        const loadcells = await ioBoardClient.getLoadcells();
        res.json({
            success: true,
            loadcells
        });
    } catch (error) {
        console.error('[IOBoard Route] Get loadcells error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 상태 조회
 * GET /api/io-board/status
 */
router.get('/status', async (req, res) => {
    try {
        const status = await ioBoardClient.getStatus();
        res.json({
            success: true,
            ...status
        });
    } catch (error) {
        console.error('[IOBoard Route] Get status error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 초기화
 * POST /api/io-board/init
 */
router.post('/init', async (req, res) => {
    try {
        const result = await ioBoardClient.init();
        res.json(result);
    } catch (error) {
        console.error('[IOBoard Route] Init error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 캘리브레이션
 * POST /api/io-board/calibrate
 */
router.post('/calibrate', async (req, res) => {
    try {
        const result = await ioBoardClient.calibrate();
        res.json(result);
    } catch (error) {
        console.error('[IOBoard Route] Calibrate error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 에러 로그 조회
 * GET /api/io-board/errors
 */
router.get('/errors', async (req, res) => {
    try {
        const errors = await ioBoardClient.getErrors();
        res.json({
            success: true,
            errors
        });
    } catch (error) {
        console.error('[IOBoard Route] Get errors error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 리부팅
 * POST /api/io-board/reboot
 */
router.post('/reboot', async (req, res) => {
    try {
        const result = await ioBoardClient.reboot();
        res.json(result);
    } catch (error) {
        console.error('[IOBoard Route] Reboot error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

module.exports = router;
