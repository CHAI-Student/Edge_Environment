/**
 * Model Service Routes
 *
 * 모델 정보, 상품 목록, 테스트 판단 API
 */

const express = require('express');
const router = express.Router();
const axios = require('axios');
const config = require('../config/key');

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

module.exports = router;
