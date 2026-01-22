/**
 * Products API - MinIO 이미지 업로드 및 MongoDB 메타데이터 저장
 */

const express = require('express');
const router = express.Router();
const multer = require('multer');
const crypto = require('crypto');
const path = require('path');

const config = require('../../config/key');
const { ProductUpload } = require('../../model/ProductUpload');

// Multer 설정 - 메모리 스토리지 사용
const upload = multer({
    storage: multer.memoryStorage(),
    limits: {
        files: 2000,        // 최대 2000개 파일
        fileSize: 100 * 1024 * 1024  // 100MB per file
    }
});

// MinIO Client (index.js에서 초기화됨)
let minioClient = null;
const BUCKET_NAME = config.minioBucket || 'chaiimage';

/**
 * MinIO 클라이언트 설정
 * @param {object} client - MinIO 클라이언트 인스턴스
 */
function setMinioClient(client) {
    minioClient = client;
}

/**
 * 문자열 안전 처리 (알파벳, 숫자, 점, 하이픈, 언더스코어만 허용)
 */
function safe(str) {
    return String(str).replace(/[^a-zA-Z0-9.\-_]/g, '_');
}

/**
 * MinIO putObject를 Promise로 래핑
 */
function putObjectAsync(bucket, key, buffer, metadata) {
    return new Promise((resolve, reject) => {
        if (!minioClient) {
            return reject(new Error('MinIO client not initialized'));
        }
        minioClient.putObject(bucket, key, buffer, metadata, (err, etag) => {
            if (err) return reject(err);
            resolve(etag);
        });
    });
}

/**
 * POST /uploads/images
 * 이미지 파일들을 MinIO에 업로드
 */
router.post('/uploads/images', upload.array('images'), async (req, res) => {
    try {
        const { productIdx, divisionIdx, rootName, relPaths } = req.body;

        // 필수 파라미터 검증
        if (!productIdx || !divisionIdx || !rootName) {
            return res.status(400).json({
                success: false,
                error: 'Missing required parameters: productIdx, divisionIdx, rootName'
            });
        }

        const files = req.files;
        if (!files || files.length === 0) {
            return res.status(400).json({
                success: false,
                error: 'No files uploaded'
            });
        }

        // relPaths 파싱 (JSON 문자열 또는 배열)
        let relativePaths;
        try {
            relativePaths = typeof relPaths === 'string' ? JSON.parse(relPaths) : relPaths;
        } catch (e) {
            relativePaths = [];
        }

        // 파일 수와 경로 수 검증
        if (relativePaths.length !== files.length) {
            console.warn(`[Products] Path count mismatch: ${relativePaths.length} paths, ${files.length} files`);
        }

        const results = [];
        const baseFolder = `productImg/${safe(productIdx)}_${safe(rootName)}`;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            let relPath = relativePaths[i] || `file_${i}`;

            // 보안: 디렉토리 탐색 방지
            relPath = relPath.replace(/^\/+/, '').replace(/\.\./g, '');

            // 파일 해시 생성 (충돌 방지)
            const hash = crypto.createHash('md5').update(file.buffer).digest('hex').substring(0, 8);
            const ext = path.extname(file.originalname) || '.jpg';
            const safeName = safe(path.basename(relPath, ext));

            const key = `${baseFolder}/${safeName}_${hash}${ext}`;

            try {
                const etag = await putObjectAsync(BUCKET_NAME, key, file.buffer, {
                    'Content-Type': file.mimetype
                });

                results.push({
                    key,
                    etag,
                    size: file.size,
                    originalName: file.originalname
                });
            } catch (uploadError) {
                console.error(`[Products] Upload failed for ${key}:`, uploadError.message);
                results.push({
                    key,
                    error: uploadError.message,
                    originalName: file.originalname
                });
            }
        }

        const successCount = results.filter(r => !r.error).length;

        res.json({
            success: true,
            productIdx,
            divisionIdx,
            folder: baseFolder,
            uploaded: successCount,
            total: files.length,
            files: results
        });

    } catch (error) {
        console.error('[Products] Upload error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * POST /products
 * MongoDB에 상품 메타데이터 저장
 */
router.post('/products', async (req, res) => {
    try {
        const {
            productIdx,
            productName,
            productEngName,
            categoryIdx,
            isNew,
            trainingStatus,
            productLoadcellWeight,
            foldername,
            folderpath,
            filelength,
            eventPromotion
        } = req.body;

        if (!productIdx) {
            return res.status(400).json({
                success: false,
                error: 'productIdx is required'
            });
        }

        const productData = {
            productIdx,
            productName,
            productEngName,
            categoryIdx: categoryIdx || 'null',
            isNew: isNew || 'true',
            trainingStatus: trainingStatus || '0',
            productLoadcellWeight: productLoadcellWeight || 'null',
            foldername,
            folderpath,
            filelength: filelength || 0,
            eventPromotion: eventPromotion || []
        };

        const product = new ProductUpload(productData);
        await product.save();

        res.json({
            success: true,
            message: 'Product metadata saved',
            product: product.toObject()
        });

    } catch (error) {
        console.error('[Products] Save error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * GET /products
 * 모든 상품 목록 조회
 */
router.get('/products', async (req, res) => {
    try {
        const products = await ProductUpload.find({}).sort({ createDate: -1 });
        res.json({
            success: true,
            count: products.length,
            products
        });
    } catch (error) {
        console.error('[Products] Query error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * GET /products/:productIdx
 * 특정 상품 조회
 */
router.get('/products/:productIdx', async (req, res) => {
    try {
        const { productIdx } = req.params;
        const product = await ProductUpload.findOne({ productIdx });

        if (!product) {
            return res.status(404).json({
                success: false,
                error: 'Product not found'
            });
        }

        res.json({
            success: true,
            product
        });
    } catch (error) {
        console.error('[Products] Query error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

module.exports = { router, setMinioClient };
