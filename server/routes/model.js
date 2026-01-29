/**
 * Model Service Routes
 *
 * 모델 정보, 상품 목록, 테스트 판단 API
 */

const express = require('express');
const router = express.Router();
const axios = require('axios');
const config = require('../config/key');
const productSyncService = require('../services/ProductSyncService');
const ioBoardClient = require('../services/IOBoardClient');
const productJudgeClient = require('../services/ProductJudgeClient');
const cameraDriverClient = require('../services/CameraDriverClient');

const MODEL_URL = config.modelUrl || 'http://localhost:8002';

/**
 * 모델 정보 조회
 * GET /api/model/info
 */
router.get('/info', async (req, res) => {
    try {
        const [healthResponse, productsResponse] = await Promise.all([
            axios.get(`${MODEL_URL}/api/health`, { timeout: 5000 }).catch(() => null),
            axios.get(`${MODEL_URL}/api/products`, { timeout: 5000 }).catch(() => null)
        ]);

        const products = productsResponse?.data?.products || [];

        res.json({
            success: true,
            healthy: healthResponse?.data?.status === 'healthy',
            model_name: healthResponse?.data?.model_loaded || 'Unknown',
            product_count: products.length,
            categories: [...new Set(products.map(p => p.category))],
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('[Model Route] Get info error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 등록된 상품 목록 조회
 * GET /api/model/products
 */
router.get('/products', async (req, res) => {
    try {
        const response = await axios.get(`${MODEL_URL}/api/products`, { timeout: 5000 });

        res.json({
            success: true,
            count: response.data.products?.length || 0,
            products: response.data.products || []
        });
    } catch (error) {
        console.error('[Model Route] Get products error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 카테고리별 상품 조회
 * GET /api/model/products/:category
 */
router.get('/products/category/:category', async (req, res) => {
    try {
        const { category } = req.params;
        const response = await axios.get(`${MODEL_URL}/api/products`, { timeout: 5000 });

        const products = (response.data.products || []).filter(
            p => p.category === category
        );

        res.json({
            success: true,
            category,
            count: products.length,
            products
        });
    } catch (error) {
        console.error('[Model Route] Get products by category error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 테스트 판단 실행
 * POST /api/model/test
 *
 * Body:
 * - zone_id: Zone ID (0-4)
 * - delta_weight: 무게 변화량 (음수 = 픽업, 양수 = 반납)
 */
router.post('/test', async (req, res) => {
    try {
        const { zone_id, delta_weight } = req.body;

        if (zone_id === undefined || delta_weight === undefined) {
            return res.status(400).json({
                success: false,
                error: 'zone_id and delta_weight are required'
            });
        }

        console.log(`[Model Route] Test judgment: zone=${zone_id}, delta=${delta_weight}g`);

        const response = await axios.post(
            `${MODEL_URL}/api/judge`,
            {
                zone_id: parseInt(zone_id),
                delta_weight: parseFloat(delta_weight)
            },
            { timeout: 30000 }
        );

        res.json({
            success: true,
            ...response.data
        });
    } catch (error) {
        console.error('[Model Route] Test judgment error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message,
            details: error.response?.data
        });
    }
});

/**
 * 히스토리 기반 판단 테스트
 * POST /api/model/test/with-history
 *
 * Body:
 * - zone_id: Zone ID
 * - delta_weight: 무게 변화량
 * - history: 이전 판단 히스토리 배열 (optional)
 */
router.post('/test/with-history', async (req, res) => {
    try {
        const { zone_id, delta_weight, history = [] } = req.body;

        if (zone_id === undefined || delta_weight === undefined) {
            return res.status(400).json({
                success: false,
                error: 'zone_id and delta_weight are required'
            });
        }

        console.log(`[Model Route] Test judgment with history: zone=${zone_id}, delta=${delta_weight}g`);

        const response = await axios.post(
            `${MODEL_URL}/api/judge/with-history`,
            {
                zone_id: parseInt(zone_id),
                delta_weight: parseFloat(delta_weight),
                history
            },
            { timeout: 30000 }
        );

        res.json({
            success: true,
            ...response.data
        });
    } catch (error) {
        console.error('[Model Route] Test judgment with history error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message,
            details: error.response?.data
        });
    }
});

/**
 * 다중 Zone 판단 테스트
 * POST /api/model/test/multi-zone
 *
 * Body:
 * - events: [{zone_id, delta_weight}, ...]
 */
router.post('/test/multi-zone', async (req, res) => {
    try {
        const { events } = req.body;

        if (!Array.isArray(events) || events.length === 0) {
            return res.status(400).json({
                success: false,
                error: 'events array is required'
            });
        }

        console.log(`[Model Route] Multi-zone test: ${events.length} events`);

        const response = await axios.post(
            `${MODEL_URL}/api/judge/multi-zone`,
            { events },
            { timeout: 30000 }
        );

        res.json({
            success: true,
            ...response.data
        });
    } catch (error) {
        console.error('[Model Route] Multi-zone test error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message,
            details: error.response?.data
        });
    }
});

/**
 * 상품 무게 검색
 * GET /api/model/search/weight/:weight
 *
 * Params:
 * - weight: 목표 무게 (g)
 *
 * Query:
 * - tolerance: 허용 오차 (default: 0.15 = 15%)
 */
router.get('/search/weight/:weight', async (req, res) => {
    try {
        const weight = parseFloat(req.params.weight);
        const tolerance = parseFloat(req.query.tolerance) || 0.15;

        const response = await axios.get(`${MODEL_URL}/api/products`, { timeout: 5000 });
        const products = response.data.products || [];

        const minWeight = weight * (1 - tolerance);
        const maxWeight = weight * (1 + tolerance);

        const matches = products.filter(p =>
            p.weight > 0 && p.weight >= minWeight && p.weight <= maxWeight
        );

        res.json({
            success: true,
            target_weight: weight,
            tolerance,
            range: { min: minWeight, max: maxWeight },
            count: matches.length,
            products: matches
        });
    } catch (error) {
        console.error('[Model Route] Search by weight error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 시연 상품 40개 동기화
 * POST /api/model/products/sync
 *
 * config/yolo_product_mapping.json에서 상품 정보를 로드하여
 * Model 서비스에 동기화합니다.
 *
 * Query:
 * - forceReload: 매핑 파일 강제 리로드 (default: false)
 */
router.post('/products/sync', async (req, res) => {
    try {
        const forceReload = req.query.forceReload === 'true';

        console.log(`[Model Route] Syncing products to Model (forceReload=${forceReload})`);

        const result = await productSyncService.syncToModel(forceReload);

        res.json({
            success: result.success,
            synced_count: result.synced_count,
            message: result.message,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('[Model Route] Sync products error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * 동기화 상태 조회
 * GET /api/model/products/sync/status
 */
router.get('/products/sync/status', async (req, res) => {
    try {
        const status = productSyncService.getStatus();

        res.json({
            success: true,
            ...status,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('[Model Route] Get sync status error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * YOLO 클래스명으로 상품 조회
 * GET /api/model/products/yolo/:className
 *
 * Params:
 * - className: YOLO 클래스 이름 (예: BAG_DALGWANG_DONUT_CHOCO_45G)
 */
router.get('/products/yolo/:className', async (req, res) => {
    try {
        const { className } = req.params;

        // 매핑 파일 로드 안됐으면 로드
        if (!productSyncService.isLoaded) {
            await productSyncService.loadMappingFile();
        }

        const product = productSyncService.getProductByYoloClassName(className);

        if (!product) {
            return res.status(404).json({
                success: false,
                error: `Product not found for YOLO class: ${className}`
            });
        }

        res.json({
            success: true,
            product,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('[Model Route] Get product by YOLO class error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * YOLO 매핑 전체 조회
 * GET /api/model/products/yolo-mapping
 *
 * Node.js에 로드된 매핑 정보를 반환합니다.
 */
router.get('/products/yolo-mapping', async (req, res) => {
    try {
        // 매핑 파일 로드 안됐으면 로드
        if (!productSyncService.isLoaded) {
            await productSyncService.loadMappingFile();
        }

        const products = productSyncService.getAllProducts();

        res.json({
            success: true,
            count: products.length,
            products,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('[Model Route] Get YOLO mapping error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Model 서비스의 YOLO 매핑 조회
 * GET /api/model/products/yolo-mapping/model
 *
 * Model 서비스에 등록된 YOLO 매핑 정보를 조회합니다.
 */
router.get('/products/yolo-mapping/model', async (req, res) => {
    try {
        const mappings = await productSyncService.getMappingsFromModel();

        res.json({
            success: true,
            count: mappings.length,
            mappings,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('[Model Route] Get Model YOLO mapping error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// ========================================
// Recording 기반 판단 API
// ========================================

/**
 * Recording 데이터로 상품 판단
 * POST /api/model/judge/recording
 *
 * IO Board의 recording 데이터를 직접 전달하면,
 * Model 서비스가 자동으로 baseline/current를 계산하고
 * delta weight를 산출하여 판단합니다.
 *
 * Body:
 * - zone_id: Zone ID (0-4)
 * - recording: Recording 데이터 배열 [{loadcells: [...], timestamp: "..."}, ...]
 * - image_folder: 스냅샷 폴더 경로 (optional)
 */
router.post('/judge/recording', async (req, res) => {
    try {
        const { zone_id, recording, image_folder } = req.body;

        if (zone_id === undefined) {
            return res.status(400).json({
                success: false,
                error: 'zone_id is required'
            });
        }

        if (!recording || !Array.isArray(recording) || recording.length === 0) {
            return res.status(400).json({
                success: false,
                error: 'recording array is required and must not be empty'
            });
        }

        console.log(`[Model Route] Judge with recording: zone=${zone_id}, samples=${recording.length}`);

        // media_paths 구성
        const mediaPaths = image_folder ? {
            image_folder,
            active_zones: [parseInt(zone_id)]
        } : null;

        const result = await productJudgeClient.judgeWithRecording({
            zone_id: parseInt(zone_id),
            recording,
            media_paths: mediaPaths
        });

        res.json({
            success: true,
            ...result
        });
    } catch (error) {
        console.error('[Model Route] Judge with recording error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message,
            details: error.response?.data
        });
    }
});

/**
 * Recording 녹화 → 판단 통합 API
 * POST /api/model/judge/record-and-judge
 *
 * IO Board에서 지정 시간 동안 로드셀 데이터를 녹화한 후
 * Model 서비스에 판단을 요청합니다.
 *
 * 흐름:
 * 1. IO Board: 녹화 시작
 * 2. 지정 시간(duration_ms) 대기
 * 3. IO Board: 녹화 중지 + 데이터 조회
 * 4. Model: Recording 데이터로 판단
 *
 * Body:
 * - zone_id: Zone ID (0-4)
 * - duration_ms: 녹화 시간 (밀리초, 기본 3000ms)
 * - include_snapshot: 스냅샷 포함 여부 (기본 true)
 */
router.post('/judge/record-and-judge', async (req, res) => {
    try {
        const { zone_id, duration_ms = 3000, include_snapshot = true } = req.body;

        if (zone_id === undefined) {
            return res.status(400).json({
                success: false,
                error: 'zone_id is required'
            });
        }

        const zoneId = parseInt(zone_id);
        const sessionId = new Date().toISOString().replace(/[-:T.Z]/g, '').substring(0, 14);

        console.log(`[Model Route] Record and judge: zone=${zoneId}, duration=${duration_ms}ms, session=${sessionId}`);

        // 1. IO Board 녹화 시작
        await ioBoardClient.startRecording();

        // 2. 스냅샷 캡처 (선택)
        let snapshotResult = null;
        if (include_snapshot) {
            try {
                snapshotResult = await cameraDriverClient.captureSnapshot(zoneId, sessionId);
            } catch (snapErr) {
                console.warn('[Model Route] Snapshot capture failed:', snapErr.message);
            }
        }

        // 3. 지정 시간 대기
        await new Promise(resolve => setTimeout(resolve, duration_ms));

        // 4. 녹화 중지 + 데이터 조회
        await ioBoardClient.stopRecording();
        const recordingData = await ioBoardClient.getRecordingData();

        if (!recordingData.logs || recordingData.logs.length === 0) {
            return res.status(400).json({
                success: false,
                error: 'No recording data collected',
                recording_samples: 0
            });
        }

        console.log(`[Model Route] Recording collected: ${recordingData.logs.length} samples`);

        // 5. Model 판단 요청
        const mediaPaths = snapshotResult ? {
            image_folder: snapshotResult.folder || snapshotResult.session_path,
            active_zones: [zoneId]
        } : null;

        const result = await productJudgeClient.judgeWithRecording({
            zone_id: zoneId,
            recording: recordingData.logs,
            media_paths: mediaPaths
        });

        res.json({
            success: true,
            session_id: sessionId,
            recording_samples: recordingData.logs.length,
            duration_ms,
            snapshot: snapshotResult,
            ...result
        });
    } catch (error) {
        console.error('[Model Route] Record and judge error:', error.message);

        // 에러 발생 시 녹화 중지 시도
        try {
            await ioBoardClient.stopRecording();
        } catch (stopErr) {
            console.warn('[Model Route] Stop recording on error failed:', stopErr.message);
        }

        res.status(500).json({
            success: false,
            error: error.message,
            details: error.response?.data
        });
    }
});

/**
 * Recording 데이터 조회 (IO Board에서)
 * GET /api/model/recording/data
 *
 * IO Board에 저장된 마지막 recording 데이터를 조회합니다.
 */
router.get('/recording/data', async (req, res) => {
    try {
        const data = await ioBoardClient.getRecordingData();

        res.json({
            success: true,
            sample_count: data.logs?.length || 0,
            logs: data.logs || []
        });
    } catch (error) {
        console.error('[Model Route] Get recording data error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Recording 상태 조회
 * GET /api/model/recording/status
 */
router.get('/recording/status', async (req, res) => {
    try {
        const status = await ioBoardClient.getRecordingStatus();

        res.json({
            success: true,
            ...status
        });
    } catch (error) {
        console.error('[Model Route] Get recording status error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Recording 시작
 * POST /api/model/recording/start
 */
router.post('/recording/start', async (req, res) => {
    try {
        const result = await ioBoardClient.startRecording();

        res.json({
            success: true,
            ...result
        });
    } catch (error) {
        console.error('[Model Route] Start recording error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Recording 중지
 * POST /api/model/recording/stop
 */
router.post('/recording/stop', async (req, res) => {
    try {
        const result = await ioBoardClient.stopRecording();

        res.json({
            success: true,
            ...result
        });
    } catch (error) {
        console.error('[Model Route] Stop recording error:', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

module.exports = router;
