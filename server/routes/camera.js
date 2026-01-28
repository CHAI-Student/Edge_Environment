/**
 * Camera Control Routes
 *
 * Node.js를 통한 카메라 제어 API 엔드포인트
 */

const express = require('express');
const router = express.Router();
const cameraClient = require('../services/CameraDriverClient');
const configManager = require('../services/ConfigManager');
const productJudgeClient = require('../services/ProductJudgeClient');

/**
 * Zone 카메라 활성화
 * POST /api/camera/zone/:zoneId/activate
 */
router.post('/zone/:zoneId/activate', async (req, res) => {
    try {
        const zoneId = parseInt(req.params.zoneId);

        if (isNaN(zoneId) || !configManager.isZoneEnabled(zoneId)) {
            const enabledZones = configManager.getEnabledZones();
            return res.status(400).json({
                success: false,
                error: `Invalid zone ID. Enabled zones: ${enabledZones.join(', ')}`
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

        if (isNaN(zoneId) || !configManager.isZoneEnabled(zoneId)) {
            const enabledZones = configManager.getEnabledZones();
            return res.status(400).json({
                success: false,
                error: `Invalid zone ID. Enabled zones: ${enabledZones.join(', ')}`
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

        if (isNaN(zoneId) || !configManager.isZoneEnabled(zoneId)) {
            const enabledZones = configManager.getEnabledZones();
            return res.status(400).json({
                success: false,
                error: `Invalid zone ID. Enabled zones: ${enabledZones.join(', ')}`
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
        const enabledCameraIds = configManager.getEnabledCameraIds();

        if (isNaN(cameraId) || !enabledCameraIds.includes(cameraId)) {
            return res.status(400).json({
                success: false,
                error: `Invalid camera ID. Enabled cameras: ${enabledCameraIds.join(', ')}`
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

/**
 * GET /api/camera/test/status
 * 카메라 테스트 모드 상태 확인
 */
router.get('/test/status', async (req, res) => {
    try {
        const [cameraHealth, modelHealth] = await Promise.allSettled([
            cameraClient.getStatus(),
            productJudgeClient.healthCheck()
        ]);

        const enabledZones = configManager.getEnabledZones();
        const enabledCameras = configManager.getEnabledCameraIds();

        res.json({
            success: true,
            mode: 'camera_only_test',
            zone_config: {
                enabled_zones: enabledZones,
                enabled_cameras: enabledCameras,
                zone_count: enabledZones.length,
                camera_count: enabledCameras.length
            },
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
                record_and_judge: 'POST /api/camera/test/record-and-judge',
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

/**
 * POST /api/camera/test/snapshot-and-judge
 * 카메라 스냅샷 촬영 후 Vision 전용 판단
 */
router.post('/test/snapshot-and-judge', async (req, res) => {
    const fs = require('fs').promises;
    const path = require('path');

    try {
        const { zone_id = 0, include_top = true } = req.body;

        // Zone 유효성 검사
        if (!configManager.isZoneEnabled(zone_id)) {
            const enabledZones = configManager.getEnabledZones();
            return res.status(400).json({
                success: false,
                error: `Invalid zone ID. Enabled zones: ${enabledZones.join(', ')}`
            });
        }

        // 세션 ID 생성 (YYMMDDHHMMSS 형식)
        const now = new Date();
        const sessionId = now.toISOString().slice(2, 19).replace(/[-T:]/g, '').slice(0, 12);

        // 1. Base64 프레임 캡처
        const captureResult = await cameraClient.captureZone(zone_id, include_top);

        // 2. Base64를 파일로 저장
        const snapshotBaseDir = process.env.SNAPSHOT_BASE_PATH || '/home/chai/Edge_Environment/data/snapshots';
        const sessionPath = path.join(snapshotBaseDir, sessionId);
        const images = {};

        // Top 카메라 이미지 저장
        if (captureResult.top_frame) {
            const topDir = path.join(sessionPath, 'cam_0');
            await fs.mkdir(topDir, { recursive: true });
            const topPath = path.join(topDir, 'snapshot.jpg');
            await fs.writeFile(topPath, Buffer.from(captureResult.top_frame, 'base64'));
            images.cam_0 = topPath;
        }

        // Side 카메라 이미지 저장
        const sideCameraId = configManager.getCameraIdForZone(zone_id);
        if (captureResult.zone_frame) {
            const sideDir = path.join(sessionPath, `cam_${sideCameraId}`);
            await fs.mkdir(sideDir, { recursive: true });
            const sidePath = path.join(sideDir, 'snapshot.jpg');
            await fs.writeFile(sidePath, Buffer.from(captureResult.zone_frame, 'base64'));
            images[`cam_${sideCameraId}`] = sidePath;
        }

        const snapshotResult = {
            success: true,
            session_id: sessionId,
            session_path: sessionPath,
            images
        };

        // 3. Model 서비스에 판단 요청 (vision_only 모드)
        const judgeResult = await productJudgeClient.judge({
            zone_id,
            vision_only: true,
            media_paths: {
                image_folder: sessionPath,
                top_image: images.cam_0,
                side_image: images[`cam_${sideCameraId}`]
            }
        });

        res.json({
            success: true,
            mode: 'camera_only',
            zone_id,
            session_id: sessionId,
            snapshot: snapshotResult,
            judgment: judgeResult
        });
    } catch (error) {
        console.error('[Camera Test] Snapshot and judge error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * POST /api/camera/test/judge-from-folder
 * 기존 이미지로 판단 테스트
 */
router.post('/test/judge-from-folder', async (req, res) => {
    try {
        const { zone_id = 0, image_folder, top_image, side_image } = req.body;

        // Zone 유효성 검사
        if (!configManager.isZoneEnabled(zone_id)) {
            const enabledZones = configManager.getEnabledZones();
            return res.status(400).json({
                success: false,
                error: `Invalid zone ID. Enabled zones: ${enabledZones.join(', ')}`
            });
        }

        const judgeResult = await productJudgeClient.judge({
            zone_id,
            vision_only: true,
            media_paths: {
                image_folder,
                top_image,
                side_image
            }
        });

        res.json({
            success: true,
            mode: 'camera_only',
            zone_id,
            judgment: judgeResult
        });
    } catch (error) {
        console.error('[Camera Test] Judge from folder error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * POST /api/camera/test/record-and-judge
 * 30fps로 3초간 90장 저장 후 모든 프레임 Vision 판단
 *
 * 단계:
 * 1. 모든 이미지 캡처 및 저장 완료
 * 2. 파일 저장 확인
 * 3. Model Service에 추론 요청
 *
 * Top 5 후보군 추출
 */
router.post('/test/record-and-judge', async (req, res) => {
    const fs = require('fs').promises;
    const fsSync = require('fs');
    const path = require('path');

    try {
        const {
            zone_id = 0,
            include_top = true,
            duration_ms = 3000,  // 녹화 시간 (기본 3초)
            fps = 30,  // 초당 프레임 수 (기본 30fps)
            top_k = 5  // 상위 후보군 개수
        } = req.body;

        // Zone 유효성 검사
        if (!configManager.isZoneEnabled(zone_id)) {
            const enabledZones = configManager.getEnabledZones();
            return res.status(400).json({
                success: false,
                error: `Invalid zone ID. Enabled zones: ${enabledZones.join(', ')}`
            });
        }

        const snapshot_interval_ms = Math.floor(1000 / fps);  // 30fps = 33ms 간격
        const numSnapshots = Math.floor(duration_ms / snapshot_interval_ms);

        console.log(`[Camera Test] Starting ${duration_ms}ms recording at ${fps}fps (${numSnapshots} frames) for Zone ${zone_id}`);

        // 세션 ID 생성
        const now = new Date();
        const sessionId = now.toISOString().slice(0, 19).replace(/[-T:]/g, '').slice(0, 15);

        // 스냅샷 저장 경로
        const snapshotBaseDir = process.env.SNAPSHOT_BASE_PATH || '/home/chai/Edge_Environment/data/snapshots';
        const sessionPath = path.join(snapshotBaseDir, sessionId);
        const sideCameraId = configManager.getCameraIdForZone(zone_id);

        // 디렉토리 미리 생성
        const cam0Dir = path.join(sessionPath, 'cam_0');
        const camSideDir = path.join(sessionPath, `cam_${sideCameraId}`);
        await fs.mkdir(cam0Dir, { recursive: true });
        await fs.mkdir(camSideDir, { recursive: true });

        console.log(`[Camera Test] ===== PHASE 1: CAPTURE =====`);
        console.log(`[Camera Test] Recording started: session=${sessionId}`);

        // ===== PHASE 1: 모든 프레임 캡처 및 저장 =====
        const snapshots = [];
        const startTime = Date.now();

        for (let i = 0; i < numSnapshots; i++) {
            const frameStartTime = Date.now();

            try {
                // Base64 프레임 캡처
                const captureResult = await cameraClient.captureZone(zone_id, include_top);
                const snapshotIndex = String(i).padStart(3, '0');

                const snapshotInfo = {
                    index: i,
                    timestamp: Date.now(),
                    images: {}
                };

                // Top 카메라 이미지 저장
                if (captureResult.top_frame) {
                    const topPath = path.join(cam0Dir, `frame_${snapshotIndex}.jpg`);
                    await fs.writeFile(topPath, Buffer.from(captureResult.top_frame, 'base64'));
                    snapshotInfo.images.cam_0 = topPath;
                }

                // Side 카메라 이미지 저장
                if (captureResult.zone_frame) {
                    const sidePath = path.join(camSideDir, `frame_${snapshotIndex}.jpg`);
                    await fs.writeFile(sidePath, Buffer.from(captureResult.zone_frame, 'base64'));
                    snapshotInfo.images[`cam_${sideCameraId}`] = sidePath;
                }

                snapshots.push(snapshotInfo);

                // 프레임 간격 유지
                const elapsed = Date.now() - frameStartTime;
                const waitTime = Math.max(0, snapshot_interval_ms - elapsed);
                if (waitTime > 0) {
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                }
            } catch (snapError) {
                console.error(`[Camera Test] Frame ${i} capture failed:`, snapError.message);
            }
        }

        const captureTime = Date.now() - startTime;
        console.log(`[Camera Test] Captured ${snapshots.length} frames in ${captureTime}ms`);

        // ===== PHASE 2: 파일 저장 완료 확인 =====
        console.log(`[Camera Test] ===== PHASE 2: VERIFY FILES =====`);

        // 파일 시스템 동기화 대기
        await new Promise(resolve => setTimeout(resolve, 500));

        // 저장된 파일 수 확인
        let savedCam0 = 0;
        let savedCamSide = 0;

        for (const snapshot of snapshots) {
            if (snapshot.images.cam_0 && fsSync.existsSync(snapshot.images.cam_0)) {
                savedCam0++;
            }
            if (snapshot.images[`cam_${sideCameraId}`] && fsSync.existsSync(snapshot.images[`cam_${sideCameraId}`])) {
                savedCamSide++;
            }
        }

        console.log(`[Camera Test] Files verified: cam_0=${savedCam0}, cam_${sideCameraId}=${savedCamSide}`);

        if (savedCam0 === 0 && savedCamSide === 0) {
            throw new Error('No images were saved');
        }

        // ===== PHASE 3: Model Service로 추론 =====
        console.log(`[Camera Test] ===== PHASE 3: INFERENCE =====`);
        console.log(`[Camera Test] Starting inference on ${snapshots.length} frames...`);

        const inferenceStartTime = Date.now();

        // 후보군 집계 (상품별 감지 횟수 및 confidence 합계)
        const candidateMap = new Map();  // productName -> { count, totalConf, detections }

        for (let i = 0; i < snapshots.length; i++) {
            const snapshot = snapshots[i];
            const topImage = snapshot.images.cam_0;
            const sideImage = snapshot.images[`cam_${sideCameraId}`];

            // 파일 존재 확인
            if (!topImage && !sideImage) continue;
            if (topImage && !fsSync.existsSync(topImage)) continue;
            if (sideImage && !fsSync.existsSync(sideImage)) continue;

            try {
                const judgeResult = await productJudgeClient.judge({
                    zone_id,
                    vision_only: true,
                    media_paths: {
                        image_folder: sessionPath,
                        top_image: topImage,
                        side_image: sideImage
                    }
                });

                // 감지된 상품들 집계
                if (judgeResult.products && judgeResult.products.length > 0) {
                    for (const product of judgeResult.products) {
                        const key = product.name || product.productId;
                        if (!candidateMap.has(key)) {
                            candidateMap.set(key, {
                                productId: product.productId,
                                name: product.name,
                                count: 0,
                                totalConf: 0,
                                maxConf: 0,
                                detections: []
                            });
                        }
                        const candidate = candidateMap.get(key);
                        candidate.count++;
                        candidate.totalConf += product.confidence || 0;
                        candidate.maxConf = Math.max(candidate.maxConf, product.confidence || 0);
                        candidate.detections.push({
                            frame: i,
                            confidence: product.confidence
                        });
                    }
                }

                // 진행 상황 로그 (10프레임마다)
                if ((i + 1) % 10 === 0) {
                    console.log(`[Camera Test] Inference progress: ${i + 1}/${snapshots.length} frames`);
                }
            } catch (judgeError) {
                console.error(`[Camera Test] Frame ${i} inference failed:`, judgeError.message);
            }
        }

        const inferenceTime = Date.now() - inferenceStartTime;
        console.log(`[Camera Test] Inference completed in ${inferenceTime}ms`);

        // ===== PHASE 4: Top K 후보군 추출 =====
        console.log(`[Camera Test] ===== PHASE 4: RESULTS =====`);

        const candidates = Array.from(candidateMap.values())
            .map(c => ({
                productId: c.productId,
                name: c.name,
                detectionCount: c.count,
                avgConfidence: c.count > 0 ? (c.totalConf / c.count) : 0,
                maxConfidence: c.maxConf,
                score: c.count * (c.totalConf / c.count),  // 감지횟수 * 평균신뢰도
                detectionRate: (c.count / snapshots.length * 100).toFixed(1) + '%'
            }))
            .sort((a, b) => b.score - a.score)
            .slice(0, top_k);

        // 로그 출력
        console.log(`\n========== Top ${top_k} Candidates ==========`);
        if (candidates.length === 0) {
            console.log(`  (No products detected)`);
        } else {
            candidates.forEach((c, idx) => {
                console.log(`#${idx + 1}: ${c.name} (ID: ${c.productId})`);
                console.log(`    Detection: ${c.detectionCount}/${snapshots.length} frames (${c.detectionRate})`);
                console.log(`    Avg Conf: ${(c.avgConfidence * 100).toFixed(1)}%, Max: ${(c.maxConfidence * 100).toFixed(1)}%`);
                console.log(`    Score: ${c.score.toFixed(2)}`);
            });
        }
        console.log(`============================================\n`);

        res.json({
            success: true,
            mode: 'camera_only_recording_30fps',
            zone_id,
            session_id: sessionId,
            recording: {
                duration_ms,
                fps,
                total_frames: snapshots.length,
                saved_frames: { cam_0: savedCam0, [`cam_${sideCameraId}`]: savedCamSide },
                actual_capture_time_ms: captureTime,
                inference_time_ms: inferenceTime,
                session_path: sessionPath
            },
            top_candidates: candidates,
            summary: {
                total_detections: Array.from(candidateMap.values()).reduce((sum, c) => sum + c.count, 0),
                unique_products: candidateMap.size,
                frames_with_detection: new Set(
                    Array.from(candidateMap.values())
                        .flatMap(c => c.detections.map(d => d.frame))
                ).size
            }
        });
    } catch (error) {
        console.error('[Camera Test] Record and judge error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

module.exports = router;
