"""
Products API Routes.

GET /api/products - 상품 목록
POST /api/products/register - 상품 등록
POST /api/products/sync - IF11 상품 동기화
"""

import time
import logging
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from database.product_db import ProductDatabase
from api.deps import get_product_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["products"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ProductInfo(BaseModel):
    """상품 정보."""

    product_id: int
    product_idx: Optional[str] = None  # IF11 product_idx (문자열 P...)
    name: str
    category: str
    weight: float
    price: int
    barcode: Optional[str] = None


class ProductListResponse(BaseModel):
    """상품 목록 응답."""

    success: bool = True
    products: List[ProductInfo]
    count: int
    timestamp: float


class ProductRegisterRequest(BaseModel):
    """상품 등록 요청."""

    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(default="snack")
    weight: float = Field(..., gt=0)
    price: int = Field(..., ge=0)
    barcode: Optional[str] = None


class ProductRegisterResponse(BaseModel):
    """상품 등록 응답."""

    success: bool = True
    product_id: int
    name: str
    timestamp: float


class IF11ProductItem(BaseModel):
    """IF11 상품 아이템 (동기화용)."""

    product_idx: str = Field(..., description="IF11 상품 ID (예: P17...)")
    product_name: str = Field(..., description="상품명")
    sale_price: int = Field(..., description="판매가")
    product_weight: Union[str, float] = Field(..., description="상품 무게 (Loadcell Weight)")


class IF11SyncRequest(BaseModel):
    """IF11 상품 동기화 요청."""

    products: List[IF11ProductItem]
    clear_existing: bool = Field(False, description="기존 상품 삭제 후 동기화")


class IF11SyncResponse(BaseModel):
    """IF11 상품 동기화 응답."""

    success: bool = True
    synced_count: int
    updated_count: int
    total_count: int
    timestamp: float


class YOLOMappingRequest(BaseModel):
    """YOLO 클래스 매핑 요청."""

    yolo_class_id: int = Field(..., description="YOLO 클래스 ID")
    yolo_class_name: str = Field(..., description="YOLO 클래스명")
    product_id: int = Field(..., description="매핑할 상품 ID (IF11 product_id)")


class YOLOMappingResponse(BaseModel):
    """YOLO 클래스 매핑 응답."""

    success: bool = True
    yolo_class_id: int
    yolo_class_name: str
    product_id: int
    timestamp: float


# ============================================================================
# Products Endpoints
# ============================================================================


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    db: ProductDatabase = Depends(get_product_db),
):
    """
    상품 목록 조회.

    Returns:
        ProductListResponse: 상품 목록
    """
    products = db.get_all_products()

    product_list = [
        ProductInfo(
            product_id=p.product_id,
            product_idx=p.product_idx,
            name=p.name,
            category=p.category,
            weight=p.weight,
            price=p.price,
            barcode=p.barcode,
        )
        for p in products
    ]

    return ProductListResponse(
        success=True,
        products=product_list,
        count=len(product_list),
        timestamp=time.time(),
    )


@router.get("/products/{product_id}", response_model=ProductInfo)
async def get_product(
    product_id: int,
    db: ProductDatabase = Depends(get_product_db),
):
    """
    상품 조회.

    Args:
        product_id: 상품 ID

    Returns:
        ProductInfo: 상품 정보
    """
    product = db.get_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductInfo(
        product_id=product.product_id,
        product_idx=product.product_idx,
        name=product.name,
        category=product.category,
        weight=product.weight,
        price=product.price,
        barcode=product.barcode,
    )


@router.post("/products/register", response_model=ProductRegisterResponse)
async def register_product(
    request: ProductRegisterRequest,
    db: ProductDatabase = Depends(get_product_db),
):
    """
    상품 등록.

    Args:
        request: 등록 요청

    Returns:
        ProductRegisterResponse: 등록 결과
    """
    product_id = db.add_product(
        name=request.name,
        category=request.category,
        weight=request.weight,
        price=request.price,
        barcode=request.barcode,
    )

    logger.info(f"Product registered: id={product_id}, name={request.name}")

    return ProductRegisterResponse(
        success=True,
        product_id=product_id,
        name=request.name,
        timestamp=time.time(),
    )


@router.post("/products/sync", response_model=IF11SyncResponse)
async def sync_products_if11(
    request: IF11SyncRequest,
    db: ProductDatabase = Depends(get_product_db),
):
    """
    IF11 상품 동기화.

    Node.js에서 받은 IF11 상품 목록을 ProductDatabase에 동기화합니다.
    YOLO 클래스와 자동 매칭을 시도합니다.

    Args:
        request: 동기화 요청

    Returns:
        IF11SyncResponse: 동기화 결과
    """
    # Pydantic 모델 리스트를 dict 리스트로 변환
    product_list = [item.dict() for item in request.products]
    
    # DB의 스마트 로더 호출 (YOLO 매칭 포함)
    added_count, updated_count = db.load_from_if11(product_list)
    
    total_count = db.product_count

    logger.info(
        f"IF11 sync complete: added={added_count}, updated={updated_count}, "
        f"total={total_count}"
    )

    return IF11SyncResponse(
        success=True,
        synced_count=added_count,   # 새로 추가된 수
        updated_count=updated_count, # 업데이트된 수
        total_count=total_count,
        timestamp=time.time(),
    )


@router.post("/products/yolo-mapping", response_model=YOLOMappingResponse)
async def register_yolo_mapping(
    request: YOLOMappingRequest,
    db: ProductDatabase = Depends(get_product_db),
):
    """
    YOLO 클래스 → IF11 상품 매핑 등록.

    YOLO 모델의 클래스 ID를 IF11 상품 ID에 매핑합니다.

    Args:
        request: 매핑 요청

    Returns:
        YOLOMappingResponse: 매핑 결과
    """
    # 상품 존재 확인
    product = db.get_product(request.product_id)
    if product is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product not found: {request.product_id}",
        )

    # 매핑 등록
    db.register_yolo_mapping(
        yolo_class_id=request.yolo_class_id,
        yolo_class_name=request.yolo_class_name,
        product_id=request.product_id,
    )

    logger.info(
        f"YOLO mapping registered: yolo_class_id={request.yolo_class_id}, "
        f"yolo_class_name={request.yolo_class_name}, "
        f"product_id={request.product_id}"
    )

    return YOLOMappingResponse(
        success=True,
        yolo_class_id=request.yolo_class_id,
        yolo_class_name=request.yolo_class_name,
        product_id=request.product_id,
        timestamp=time.time(),
    )


@router.get("/products/yolo-mappings")
async def list_yolo_mappings(
    db: ProductDatabase = Depends(get_product_db),
):
    """
    YOLO 클래스 매핑 목록 조회.

    Returns:
        매핑 목록
    """
    mappings = db.get_yolo_mappings()

    return {
        "success": True,
        "mappings": mappings,
        "count": len(mappings),
        "timestamp": time.time(),
    }