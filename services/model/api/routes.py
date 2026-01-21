"""
API Routes for Model Service.

REST API 엔드포인트 정의.

엔드포인트:
- GET /api/health: 헬스 체크
- POST /api/judge: 상품 판단 요청 (Node.js에서 호출)
- GET /api/products: 상품 목록
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging
import time

from ..config import config
from ..database.product_db import ProductDatabase
from ..engine import ProductDecisionEngine, EnsembleResult, JudgmentStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["model"])


# Request/Response Models
class ProductItem(BaseModel):
    """상품 정보 (요청용)."""
    id: int
    name: str
    weight: float
    price: int
    stock: int = 0


class JudgeRequest(BaseModel):
    """상품 판단 요청."""
    snapshot_folder: Optional[str] = None
    loadcell_weights: List[str] = Field(default_factory=list)
    baseline_weights: List[str] = Field(default_factory=list)
    zone_id: int = 0
    products: List[ProductItem] = Field(default_factory=list)
    delta_weight: Optional[float] = None  # 직접 무게 변화량 지정
    vision_candidates: Optional[List[dict]] = None  # 직접 Vision 후보군 지정


class ProductJudgmentResponse(BaseModel):
    """개별 상품 판단 결과."""
    productId: int
    name: str
    count: int
    unitPrice: int
    totalPrice: int
    confidence: float


class WeightInfoResponse(BaseModel):
    """무게 정보."""
    delta: float
    explained: float
    residual: float


class JudgeResponse(BaseModel):
    """상품 판단 응답."""
    success: bool
    products: List[ProductJudgmentResponse]
    totalPrice: int
    status: str  # complete, partial, uncertain, no_detection
    confidence: float
    weightInfo: WeightInfoResponse
    productCount: int
    isRemoval: bool
    timestamp: float


class HealthResponse(BaseModel):
    """헬스 체크 응답."""
    status: str
    service: str
    version: str
    timestamp: float


class ProductInfoResponse(BaseModel):
    """상품 정보 (응답용)."""
    product_id: int
    name: str
    category: str
    weight: float
    price: int


# Global instances (initialized in main.py)
_product_db: Optional[ProductDatabase] = None
_decision_engine: Optional[ProductDecisionEngine] = None


def init_routes(product_db: ProductDatabase, decision_engine: ProductDecisionEngine):
    """라우터 초기화 (main.py에서 호출)."""
    global _product_db, _decision_engine
    _product_db = product_db
    _decision_engine = decision_engine
    logger.info("API routes initialized")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """헬스 체크."""
    return HealthResponse(
        status="healthy",
        service="model",
        version="1.0.0",
        timestamp=time.time(),
    )


@router.post("/judge", response_model=JudgeResponse)
async def judge_products(request: JudgeRequest):
    """
    상품 판단 수행.

    Node.js Orchestrator에서 호출하여 상품을 판단합니다.

    Args:
        request: 판단 요청 (loadcell_weights, baseline_weights, zone_id, products)

    Returns:
        JudgeResponse: 판단 결과
    """
    global _product_db, _decision_engine

    if _decision_engine is None:
        raise HTTPException(status_code=503, detail="Decision engine not initialized")

    logger.info(f"Judge request: zone_id={request.zone_id}")

    try:
        # 1. 무게 변화량 계산
        if request.delta_weight is not None:
            delta_weight = request.delta_weight
        else:
            delta_weight = _calculate_delta_weight(
                request.loadcell_weights,
                request.baseline_weights,
                request.zone_id,
            )

        logger.info(f"Zone {request.zone_id} delta_weight: {delta_weight:.1f}g")

        # 2. Vision 후보군 생성
        if request.vision_candidates:
            vision_candidates = [
                EnsembleResult(
                    class_id=c.get("class_id", 0),
                    class_name=c.get("class_name", "unknown"),
                    top_confidence=c.get("top_confidence", 0.0),
                    side_confidence=c.get("side_confidence", 0.0),
                    combined_confidence=c.get("combined_confidence", 0.5),
                    vote_count=c.get("vote_count", 1),
                )
                for c in request.vision_candidates
            ]
        else:
            # 실제 Vision 추론이 필요한 경우 여기서 처리
            # 현재는 빈 리스트로 반환 (실제 구현 시 camera + YOLO 파이프라인 연동)
            vision_candidates = []
            logger.warning("No vision candidates provided, using empty list")

        # 3. 판단 수행
        result = _decision_engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=delta_weight,
        )

        # 4. 응답 변환
        response = JudgeResponse(
            success=result.is_success,
            products=[
                ProductJudgmentResponse(
                    productId=p.product_id,
                    name=p.name,
                    count=p.count,
                    unitPrice=p.unit_price,
                    totalPrice=p.total_price,
                    confidence=round(p.confidence, 2),
                )
                for p in result.products
            ],
            totalPrice=result.total_price,
            status=result.status.value,
            confidence=round(result.confidence, 2),
            weightInfo=WeightInfoResponse(
                delta=round(result.weight_delta, 1),
                explained=round(result.weight_explained, 1),
                residual=round(result.weight_residual, 1),
            ),
            productCount=result.product_count,
            isRemoval=result.is_removal,
            timestamp=result.timestamp,
        )

        logger.info(
            f"Judge result: status={result.status.value}, "
            f"products={len(result.products)}, totalPrice={result.total_price}"
        )

        return response

    except Exception as e:
        logger.error(f"Judge failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products", response_model=List[ProductInfoResponse])
async def list_products():
    """등록된 상품 목록 조회."""
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    products = _product_db.get_all_products(exclude_hand=True)

    return [
        ProductInfoResponse(
            product_id=p.product_id,
            name=p.name,
            category=p.category,
            weight=p.weight,
            price=p.price,
        )
        for p in products
    ]


@router.get("/products/{product_id}", response_model=ProductInfoResponse)
async def get_product(product_id: int):
    """특정 상품 정보 조회."""
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    product = _product_db.get_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    return ProductInfoResponse(
        product_id=product.product_id,
        name=product.name,
        category=product.category,
        weight=product.weight,
        price=product.price,
    )


def _calculate_delta_weight(
    loadcell_weights: List[str],
    baseline_weights: List[str],
    zone_id: int,
) -> float:
    """
    Zone별 무게 변화량 계산.

    Args:
        loadcell_weights: 현재 로드셀 무게 리스트 (예: ["+00432", "+00433", ...])
        baseline_weights: 기준 무게 리스트
        zone_id: Zone ID

    Returns:
        무게 변화량 (현재 - 기준, 음수 = 감소)
    """
    from ..config import ZONE_CHANNEL_MAP

    channels = ZONE_CHANNEL_MAP.get(zone_id, [])

    if not channels:
        logger.warning(f"No channels mapped for zone {zone_id}")
        return 0.0

    current_sum = 0.0
    baseline_sum = 0.0

    for ch in channels:
        if ch < len(loadcell_weights):
            current_sum += _parse_weight_str(loadcell_weights[ch])
        if ch < len(baseline_weights):
            baseline_sum += _parse_weight_str(baseline_weights[ch])

    delta = current_sum - baseline_sum

    logger.debug(
        f"Zone {zone_id}: channels={channels}, "
        f"current={current_sum:.1f}g, baseline={baseline_sum:.1f}g, delta={delta:.1f}g"
    )

    return delta


def _parse_weight_str(weight_str: str) -> float:
    """
    무게 문자열 파싱.

    Args:
        weight_str: 무게 문자열 (예: "+00432", "-00180")

    Returns:
        무게 값 (g)
    """
    try:
        # 부호 포함 정수로 파싱
        return float(weight_str)
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse weight string: {weight_str}")
        return 0.0
