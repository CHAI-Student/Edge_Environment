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
const cameraClient = require('../services/CameraDriverClient');

const IO_BOARD_URL = config.ioBoardUrl || 'http://localhost:8000';

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
 *
 * 데드볼트 잠금 해제 시 Top 카메라 (cam_0) 활성화 및 녹화 시작
 */
router.post('/deadbolt/unlock', async (req, res) => {
    try {
        // 1. IO Board에 데드볼트 열기 명령
        const response = await axios.post(
            `${IO_BOARD_URL}/deadbolt`,
            { action: 'OPEN' },
            { timeout: 5000 }
        );

        console.log('[Door Route] Deadbolt unlocked');

        // 2. Top 카메라 활성화 및 녹화 시작 (비동기로 처리)
        let topCameraResult = null;
        try {
            // Top 카메라 활성화
            await cameraClient.activateTopCamera();

            // 녹화 세션 시작
            const sessionId = new Date().toISOString()
                .replace(/[-:T.Z]/g, '')
                .slice(2, 14);

            const recordingResult = await cameraClient.startTopCameraRecording(sessionId);
            topCameraResult = {
                activated: true,
                session_id: recordingResult.session_id || sessionId
            };

            console.log(`[Door Route] Top camera activated and recording started: session=${topCameraResult.session_id}`);

            // IOBoardSSESubscriber에 상태 동기화
            ioBoardSSE.topCameraActive = true;
            ioBoardSSE.topCameraRecordingSession = topCameraResult.session_id;

        } catch (cameraError) {
            console.error('[Door Route] Top camera activation error:', cameraError.message);
            topCameraResult = {
                activated: false,
                error: cameraError.message
            };
        }

        res.json({
            success: true,
            state: response.data.state,
            message: 'Deadbolt unlocked',
            topCamera: topCameraResult
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
 *
 * 데드볼트 잠금 시 Top 카메라 비활성화 스케줄링 (10초 후)
 */
router.post('/deadbolt/lock', async (req, res) => {
    try {
        // 1. IO Board에 데드볼트 닫기 명령
        const response = await axios.post(
            `${IO_BOARD_URL}/deadbolt`,
            { action: 'CLOSE' },
            { timeout: 5000 }
        );

        console.log('[Door Route] Deadbolt locked');

        // 2. Top 카메라 비활성화 스케줄링 (IOBoardSSESubscriber에 위임)
        ioBoardSSE._scheduleTopCameraDeactivation();

        res.json({
            success: true,
            state: response.data.state,
            message: 'Deadbolt locked',
            topCamera: {
                deactivation_scheduled: true,
                delay_ms: ioBoardSSE.cameraDeactivateDelay
            }
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
 *
 * 상태에 따라 Top 카메라 활성화/비활성화 처리
 */
router.post('/deadbolt/toggle', async (req, res) => {
    try {
        // 현재 상태 확인
        const statusResponse = await axios.get(`${IO_BOARD_URL}/status`, { timeout: 5000 });
        const currentState = statusResponse.data.deadbolt;

        // 상태 반전
        const isOpening = currentState.toUpperCase().includes('CLOSE') ||
                          currentState.toUpperCase().includes('LOCK');
        const newState = isOpening ? 'OPEN' : 'CLOSE';

        const response = await axios.post(
            `${IO_BOARD_URL}/deadbolt`,
            { action: newState },
            { timeout: 5000 }
        );

        console.log(`[Door Route] Deadbolt toggled: ${currentState} -> ${newState}`);

        // Top 카메라 제어
        let topCameraResult = null;

        if (isOpening) {
            // 열림 -> Top 카메라 활성화 + 녹화
            try {
                await cameraClient.activateTopCamera();
                const sessionId = new Date().toISOString()
                    .replace(/[-:T.Z]/g, '')
                    .slice(2, 14);
                const recordingResult = await cameraClient.startTopCameraRecording(sessionId);

                ioBoardSSE.topCameraActive = true;
                ioBoardSSE.topCameraRecordingSession = recordingResult.session_id || sessionId;

                topCameraResult = {
                    activated: true,
                    session_id: recordingResult.session_id || sessionId
                };
            } catch (cameraError) {
                topCameraResult = { activated: false, error: cameraError.message };
            }
        } else {
            // 닫힘 -> Top 카메라 비활성화 스케줄링
            ioBoardSSE._scheduleTopCameraDeactivation();
            topCameraResult = {
                deactivation_scheduled: true,
                delay_ms: ioBoardSSE.cameraDeactivateDelay
            };
        }

        res.json({
            success: true,
            previousState: currentState,
            state: response.data.state,
            message: `Deadbolt toggled to ${newState}`,
            topCamera: topCameraResult
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
