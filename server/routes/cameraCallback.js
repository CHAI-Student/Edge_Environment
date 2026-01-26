/**
 * Camera Callback Route
 *
 * Camera Driver가 이미지/영상 저장 완료 후 이 엔드포인트로 알림을 보냅니다.
 * WeightChangeAccumulator를 통해 10초 타이머와 이벤트 누적을 처리합니다.
 *
 * POST /api/camera/media-ready
 * Body: {
 *     zone_id: number,
 *     session_id: string,
 *     weight_data: {
 *         before_weights: number[],
 *         after_weights: number[],
 *         delta_weight: number,
 *         channels: number[]
 *     },
 *     media_paths: {
 *         base_path: string,
 *         images: { cam_0: string, cam_1: string, ... },
 *         videos: { cam_0: string, cam_1: string, ... }
 *     },
 *     timestamp: number
 * }
 */

const express = require('express');
const router = express.Router();
const weightAccumulator = require('../services/WeightChangeAccumulator');
const productJudgeClient = require('../services/ProductJudgeClient');
const cameraDriverClient = require('../services/CameraDriverClient');

/**
 * POST /api/camera/media-ready
 *
 * Camera Driver로부터 미디어 저장 완료 알림을 받습니다.
 */
router.post('/media-ready', async (req, res) => {
    try {
        const {
            zone_id,
            session_id,
            weight_data,
            media_paths,
            timestamp
        } = req.body;

        // 유효성 검사
        if (zone_id === undefined || zone_id === null) {
            return res.status(400).json({
                success: false,
                error: 'zone_id is required'
            });
        }

        console.log(
            `[CameraCallback] media-ready received: ` +
            `Zone ${zone_id}, session=${session_id}, delta=${weight_data?.delta_weight}g`
        );

        // WeightChangeAccumulator에 이벤트 추가
        await weightAccumulator.addEvent(
            zone_id,
            weight_data,
            media_paths,
            session_id
        );

        res.json({
            success: true,
            message: 'Event received and accumulated',
            zone_id: zone_id,
            session_id: session_id,
            pending_count: weightAccumulator.getStatus().pending_events,
            timestamp: Date.now()
        });

    } catch (error) {
        console.error('[CameraCallback] Error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * GET /api/camera/accumulator/status
 *
 * WeightChangeAccumulator 상태 조회
 */
router.get('/accumulator/status', (req, res) => {
    try {
        const status = weightAccumulator.getStatus();
        res.json({
            success: true,
            status: status,
            timestamp: Date.now()
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * POST /api/camera/accumulator/force-process
 *
 * 대기 중인 이벤트 강제 처리 (테스트/디버깅용)
 */
router.post('/accumulator/force-process', async (req, res) => {
    try {
        const result = await weightAccumulator.forceProcess();
        res.json({
            success: true,
            result: result,
            timestamp: Date.now()
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * POST /api/camera/accumulator/reset
 *
 * WeightChangeAccumulator 상태 초기화
 */
router.post('/accumulator/reset', (req, res) => {
    try {
        weightAccumulator.reset();
        res.json({
            success: true,
            message: 'Accumulator reset',
            timestamp: Date.now()
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// =============================================================================
// Camera-Only Testing (로드셀 없이 카메라만으로 테스트)
// =============================================================================

/**
 * POST /api/camera/test/snapshot-and-judge
 *
 * 카메라 스냅샷 촬영 후 Vision 전용 판단 (로드셀 없음)
 * 로드셀 연결 없이 카메라 시스템만 테스트할 때 사용합니다.
 *
 * Body: {
 *     zone_id: number (0-4),
 *     include_top: boolean (default: true)
 * }
 */
router.post('/test/snapshot-and-judge', async (req, res) => {
    try {
        const { zone_id = 0, include_top = true } = req.body;

        console.log(`[CameraTest] Starting camera-only test for zone ${zone_id}`);

        // 1. 세션 ID 생성 (YYMMDDHHMMSS 형식)
        const now = new Date();
        const sessionId = [
            String(now.getFullYear()).slice(-2),
            String(now.getMonth() + 1).padStart(2, '0'),
            String(now.getDate()).padStart(2, '0'),
            String(now.getHours()).padStart(2, '0'),
            String(now.getMinutes()).padStart(2, '0'),
            String(now.getSeconds()).padStart(2, '0'),
        ].join('');

        // 2. 카메라 스냅샷 촬영
        console.log(`[CameraTest] Capturing snapshot: session=${sessionId}`);
        const snapshotResult = await cameraDriverClient.captureSnapshot(
            zone_id,
            sessionId,
            include_top
        );

        console.log(`[CameraTest] Snapshot captured: ${JSON.stringify(snapshotResult.images || snapshotResult)}`);

        // 3. 카메라 전용 판단 요청 (Vision-only)
        // captureSnapshot은 session_path와 images를 반환
        const media_paths = {
            image_folder: snapshotResult.session_path || snapshotResult.base_path,
            top_image: snapshotResult.images?.cam_0 || null,
            side_image: snapshotResult.images?.[`cam_${zone_id + 1}`] || null
        };

        console.log(`[CameraTest] Requesting camera-only judgment: ${JSON.stringify(media_paths)}`);

        const judgeResult = await productJudgeClient.judgeWithCameraOnly({
            zone_id: zone_id,
            media_paths: media_paths,
            timestamp: Date.now() / 1000,
            inference_id: `test_${sessionId}`
        });

        console.log(
            `[CameraTest] Judgment complete: status=${judgeResult.status}, ` +
            `products=${judgeResult.products?.length || 0}, confidence=${judgeResult.confidence}`
        );

        res.json({
            success: true,
            mode: 'camera_only',
            zone_id: zone_id,
            session_id: sessionId,
            snapshot: {
                session_path: snapshotResult.session_path,
                images: snapshotResult.images
            },
            judgment: judgeResult,
            timestamp: Date.now()
        });

    } catch (error) {
        console.error('[CameraTest] Error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message,
            stack: process.env.NODE_ENV === 'development' ? error.stack : undefined
        });
    }
});

/**
 * POST /api/camera/test/judge-from-folder
 *
 * 기존 스냅샷 폴더로 Vision 전용 판단 (로드셀 없음)
 * 이미 저장된 이미지로 판단을 테스트할 때 사용합니다.
 *
 * Body: {
 *     zone_id: number (0-4),
 *     image_folder: string (스냅샷 폴더 경로),
 *     top_image: string (optional, Top 카메라 이미지 경로),
 *     side_image: string (optional, Side 카메라 이미지 경로)
 * }
 */
router.post('/test/judge-from-folder', async (req, res) => {
    try {
        const {
            zone_id = 0,
            image_folder,
            top_image,
            side_image
        } = req.body;

        if (!image_folder && !top_image && !side_image) {
            return res.status(400).json({
                success: false,
                error: 'Either image_folder or image paths (top_image/side_image) required'
            });
        }

        console.log(`[CameraTest] Judging from folder: ${image_folder || 'individual paths'}`);

        const media_paths = {
            image_folder: image_folder || null,
            top_image: top_image || null,
            side_image: side_image || null
        };

        const judgeResult = await productJudgeClient.judgeWithCameraOnly({
            zone_id: zone_id,
            media_paths: media_paths,
            timestamp: Date.now() / 1000
        });

        console.log(
            `[CameraTest] Judgment complete: status=${judgeResult.status}, ` +
            `products=${judgeResult.products?.length || 0}`
        );

        res.json({
            success: true,
            mode: 'camera_only',
            zone_id: zone_id,
            media_paths: media_paths,
            judgment: judgeResult,
            timestamp: Date.now()
        });

    } catch (error) {
        console.error('[CameraTest] Error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * GET /api/camera/test/status
 *
 * 카메라 테스트 모드 상태 확인
 */
router.get('/test/status', async (req, res) => {
    try {
        // 각 서비스 연결 상태 확인
        const [cameraHealth, modelHealth] = await Promise.allSettled([
            cameraDriverClient.getStatus(),  // CameraDriverClient는 getStatus 사용
            productJudgeClient.healthCheck()
        ]);

        res.json({
            success: true,
            mode: 'camera_only_test',
            services: {
                camera_driver: {
                    healthy: cameraHealth.status === 'fulfilled',
                    status: cameraHealth.status === 'fulfilled' ? cameraHealth.value : cameraHealth.reason?.message
                },
                model_service: {
                    healthy: modelHealth.status === 'fulfilled',
                    status: modelHealth.status === 'fulfilled' ? modelHealth.value : modelHealth.reason?.message
                }
            },
            note: 'Camera-only mode: loadcell not required',
            endpoints: {
                snapshot_and_judge: 'POST /api/camera/test/snapshot-and-judge',
                judge_from_folder: 'POST /api/camera/test/judge-from-folder'
            },
            timestamp: Date.now()
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

module.exports = router;
