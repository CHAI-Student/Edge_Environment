/**
 * Door Control Routes
 *
 * 데드볼트 제어 및 문/데드볼트 상태 조회 API
 */

const express = require('express');
const router = express.Router();
const axios = require('axios');
const config = require('../config/key');
const ioBoardSSE = require('../services/IOBoardSSESubscriber');

const IO_BOARD_URL = config.ioBoardUrl || 'http://localhost:8001';

/**
 * 문/데드볼트 상태 조회
 * GET /api/door/status
 */
router.get('/status', async (req, res) => {
    try {
        // SSE 구독자에서 캐시된 상태가 있으면 반환
        const sseStatus = ioBoardSSE.getStatus();
        if (sseStatus.doorState && sseStatus.deadboltState) {
            return res.json({
                success: true,
                door: sseStatus.doorState,
                deadbolt: sseStatus.deadboltState,
                timestamp: sseStatus.lastDoorUpdateTime,
                source: 'cache'
            });
        }

        // IO Board에서 직접 조회
        const response = await axios.get(`${IO_BOARD_URL}/status`, { timeout: 5000 });
        res.json({
            success: true,
            door: response.data.door,
            deadbolt: response.data.deadbolt,
            timestamp: new Date().toISOString(),
            source: 'io_board'
        });
    } catch (error) {
        console.error('[Door Route] Get status error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 데드볼트 잠금 해제
 * POST /api/door/deadbolt/unlock
 */
router.post('/deadbolt/unlock', async (req, res) => {
    try {
        const response = await axios.post(
            `${IO_BOARD_URL}/deadbolt`,
            { state: 'OPEN' },
            { timeout: 5000 }
        );

        console.log('[Door Route] Deadbolt unlocked');
        res.json({
            success: true,
            state: response.data.state,
            message: 'Deadbolt unlocked'
        });
    } catch (error) {
        console.error('[Door Route] Unlock error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 데드볼트 잠금
 * POST /api/door/deadbolt/lock
 */
router.post('/deadbolt/lock', async (req, res) => {
    try {
        const response = await axios.post(
            `${IO_BOARD_URL}/deadbolt`,
            { state: 'CLOSE' },
            { timeout: 5000 }
        );

        console.log('[Door Route] Deadbolt locked');
        res.json({
            success: true,
            state: response.data.state,
            message: 'Deadbolt locked'
        });
    } catch (error) {
        console.error('[Door Route] Lock error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 데드볼트 토글 (현재 상태 반전)
 * POST /api/door/deadbolt/toggle
 */
router.post('/deadbolt/toggle', async (req, res) => {
    try {
        // 현재 상태 확인
        const statusResponse = await axios.get(`${IO_BOARD_URL}/status`, { timeout: 5000 });
        const currentState = statusResponse.data.deadbolt;

        // 상태 반전
        const newState = currentState.toUpperCase().includes('OPEN') ? 'CLOSE' : 'OPEN';

        const response = await axios.post(
            `${IO_BOARD_URL}/deadbolt`,
            { state: newState },
            { timeout: 5000 }
        );

        console.log(`[Door Route] Deadbolt toggled: ${currentState} -> ${newState}`);
        res.json({
            success: true,
            previousState: currentState,
            state: response.data.state,
            message: `Deadbolt toggled to ${newState}`
        });
    } catch (error) {
        console.error('[Door Route] Toggle error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

module.exports = router;
