/**
 * ProductSyncService - 상품 정보 동기화 서비스
 *
 * Node.js에서 상품 정보를 관리하고 Model 서비스와 동기화합니다.
 *
 * 주요 기능:
 * - config/yolo_product_mapping.json에서 40개 시연 상품 로드
 * - Model 서비스(/api/products/sync)에 상품 정보 전달
 * - YOLO class_name → 상품 정보 매핑
 *
 * 사용 예시:
 *   const productSyncService = require('./services/ProductSyncService');
 *   await productSyncService.syncToModel();
 *   const product = productSyncService.getProductByYoloClassName('BAG_DALGWANG_DONUT_CHOCO_45G');
 */

const axios = require('axios');
const fs = require('fs');
const path = require('path');
const config = require('../config/key');

class ProductSyncService {
    constructor() {
        this.modelUrl = config.productJudgeUrl || 'http://localhost:8002';
        this.mappingFilePath = path.join(__dirname, '../../config/yolo_product_mapping.json');
        this.products = [];  // 로드된 상품 목록
        this.yoloNameToProduct = {};  // yolo_class_name → product 매핑
        this.yoloIdToProduct = {};    // yolo_class_id → product 매핑
        this.isLoaded = false;
        this.lastSyncTime = null;
    }

    /**
     * 매핑 파일에서 상품 정보 로드
     * @returns {Promise<number>} 로드된 상품 수
     */
    async loadMappingFile() {
        try {
            if (!fs.existsSync(this.mappingFilePath)) {
                console.warn('[ProductSyncService] Mapping file not found:', this.mappingFilePath);
                return 0;
            }

            const data = JSON.parse(fs.readFileSync(this.mappingFilePath, 'utf-8'));
            const mappings = data.mappings || [];

            this.products = [];
            this.yoloNameToProduct = {};
            this.yoloIdToProduct = {};

            for (const mapping of mappings) {
                if (!mapping.yolo_class_id || !mapping.yolo_class_name) {
                    continue;
                }

                const product = {
                    yolo_class_id: mapping.yolo_class_id,
                    yolo_class_name: mapping.yolo_class_name,
                    product_name: mapping.product_name || mapping.yolo_class_name,
                    category: mapping.category || 'etc',
                    weight: mapping.weight || 0,
                    price: mapping.price || 1000,
                };

                this.products.push(product);
                this.yoloNameToProduct[mapping.yolo_class_name] = product;
                this.yoloIdToProduct[mapping.yolo_class_id] = product;
            }

            this.isLoaded = true;
            console.log(`[ProductSyncService] Loaded ${this.products.length} products from mapping file`);
            return this.products.length;
        } catch (error) {
            console.error('[ProductSyncService] Failed to load mapping file:', error.message);
            return 0;
        }
    }

    /**
     * Model 서비스에 상품 정보 동기화
     *
     * IF11 형식으로 상품 리스트를 Model 서비스에 전달합니다.
     * yolo_class_name 필드가 있으면 Model에서 자동으로 YOLO class_id와 매핑합니다.
     *
     * @param {boolean} forceReload - 매핑 파일 강제 리로드
     * @returns {Promise<{success: boolean, synced_count: number, message: string}>}
     */
    async syncToModel(forceReload = false) {
        try {
            // 매핑 파일 로드 (필요시)
            if (!this.isLoaded || forceReload) {
                await this.loadMappingFile();
            }

            if (this.products.length === 0) {
                return {
                    success: false,
                    synced_count: 0,
                    message: 'No products to sync',
                };
            }

            // IF11 형식으로 변환
            const productList = this.products.map((p, index) => ({
                product_idx: `DEMO_${p.yolo_class_id}`,  // 시연용 ID 생성
                product_name: p.product_name,
                sale_price: p.price,
                stock_qty: 10,  // 기본 재고
                product_weight: String(p.weight),
                // 추가 필드 (Model에서 매핑용)
                yolo_class_id: p.yolo_class_id,
                yolo_class_name: p.yolo_class_name,
                category: p.category,
            }));

            // Model 서비스에 동기화 요청
            const response = await axios.post(
                `${this.modelUrl}/api/products/sync`,
                { product_list: productList },
                { timeout: 30000 }
            );

            this.lastSyncTime = new Date();

            console.log(`[ProductSyncService] Synced ${response.data.loaded_count || 0} products to Model`);

            return {
                success: true,
                synced_count: response.data.loaded_count || this.products.length,
                message: response.data.message || 'Products synced successfully',
            };
        } catch (error) {
            console.error('[ProductSyncService] Sync to Model failed:', error.message);
            return {
                success: false,
                synced_count: 0,
                message: error.message,
            };
        }
    }

    /**
     * YOLO 클래스 이름으로 상품 조회
     * @param {string} yoloClassName - YOLO 클래스 이름 (예: "BAG_DALGWANG_DONUT_CHOCO_45G")
     * @returns {Object|null} 상품 정보 또는 null
     */
    getProductByYoloClassName(yoloClassName) {
        return this.yoloNameToProduct[yoloClassName] || null;
    }

    /**
     * YOLO 클래스 ID로 상품 조회
     * @param {number} yoloClassId - YOLO 클래스 ID
     * @returns {Object|null} 상품 정보 또는 null
     */
    getProductByYoloClassId(yoloClassId) {
        return this.yoloIdToProduct[yoloClassId] || null;
    }

    /**
     * 전체 상품 목록 조회
     * @returns {Array} 상품 목록
     */
    getAllProducts() {
        return [...this.products];
    }

    /**
     * 상품 수 조회
     * @returns {number}
     */
    getProductCount() {
        return this.products.length;
    }

    /**
     * 동기화 상태 조회
     * @returns {Object} 동기화 상태
     */
    getStatus() {
        return {
            isLoaded: this.isLoaded,
            productCount: this.products.length,
            lastSyncTime: this.lastSyncTime,
            mappingFilePath: this.mappingFilePath,
        };
    }

    /**
     * 특정 상품 가격 업데이트
     * @param {number} yoloClassId - YOLO 클래스 ID
     * @param {number} newPrice - 새 가격
     * @returns {boolean} 업데이트 성공 여부
     */
    updatePrice(yoloClassId, newPrice) {
        const product = this.yoloIdToProduct[yoloClassId];
        if (product) {
            product.price = newPrice;
            return true;
        }
        return false;
    }

    /**
     * 특정 상품 무게 업데이트
     * @param {number} yoloClassId - YOLO 클래스 ID
     * @param {number} newWeight - 새 무게 (g)
     * @returns {boolean} 업데이트 성공 여부
     */
    updateWeight(yoloClassId, newWeight) {
        const product = this.yoloIdToProduct[yoloClassId];
        if (product) {
            product.weight = newWeight;
            return true;
        }
        return false;
    }

    /**
     * Model 서비스에서 YOLO 매핑 로드
     *
     * Model 서비스의 /api/products/yolo-mapping/load를 호출하여
     * 저장된 매핑 파일을 로드합니다.
     *
     * @returns {Promise<{success: boolean, loaded_count: number}>}
     */
    async loadMappingFromModel() {
        try {
            const response = await axios.post(
                `${this.modelUrl}/api/products/yolo-mapping/load`,
                {},
                { timeout: 10000 }
            );

            return {
                success: true,
                loaded_count: response.data.loaded_count || 0,
            };
        } catch (error) {
            console.error('[ProductSyncService] Load mapping from Model failed:', error.message);
            return {
                success: false,
                loaded_count: 0,
            };
        }
    }

    /**
     * Model 서비스에 YOLO 매핑 저장
     *
     * Model 서비스의 /api/products/yolo-mapping/save를 호출하여
     * 현재 매핑을 파일로 저장합니다.
     *
     * @returns {Promise<{success: boolean, message: string}>}
     */
    async saveMappingToModel() {
        try {
            const response = await axios.post(
                `${this.modelUrl}/api/products/yolo-mapping/save`,
                {},
                { timeout: 10000 }
            );

            return {
                success: true,
                message: response.data.message || 'Mapping saved',
            };
        } catch (error) {
            console.error('[ProductSyncService] Save mapping to Model failed:', error.message);
            return {
                success: false,
                message: error.message,
            };
        }
    }

    /**
     * Model 서비스의 전체 YOLO 매핑 조회
     * @returns {Promise<Array>} 매핑 리스트
     */
    async getMappingsFromModel() {
        try {
            const response = await axios.get(
                `${this.modelUrl}/api/products/yolo-mapping`,
                { timeout: 10000 }
            );

            return response.data.mappings || [];
        } catch (error) {
            console.error('[ProductSyncService] Get mappings from Model failed:', error.message);
            return [];
        }
    }
}

module.exports = new ProductSyncService();
