"""
Multi-Zone Judge API Routes (v4.0).

POST /api/judge/multi-zone - Node.js에서 10초 간격으로 폴링
SessionStore에서 결과를 조회하여 반환.

사용 흐름:
1. Node.js가 데드볼트 문 열림 감지
2. 10초 간격으로 /api/judge/multi-zone 폴링
3. 세션 없으면 "processing" 반환
4. 세션 있으면 "complete" + 상품 정보 반환
"""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from session import SessionStore
from api.deps import get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/judge", tags=["judge"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ProductInfo(BaseModel):
    """Node.js에서 전달하는 상품 정보."""

    product_idx: str = Field(..., description="상품 ID (IF11)")
    product_name: str = Field(..., description="상품명")
    sale_price: int = Field(..., description="판매가격")
    product_weight: str = Field(..., description="상품 무게 (g)")


class MultiZoneRequest(BaseModel):
    """Multi-Zone 판단 요청."""

    session_id: str = Field(..., description="세션 ID (zone_{zone}_{YYMMDD}_{HHMMSS})")
    products: List[ProductInfo] = Field(
        default_factory=list,
        description="상품 목록 (선택, 무게 검증용)",
    )


class ProductResponse(BaseModel):
    """상품 판단 결과."""

    productIdx: str  # IF11 product_idx (문자열)
    productId: int   # YOLO class_id (하위 호환)
    name: str
    count: int
    price: int
    confidence: float = 0.0


class ProcessingResponse(BaseModel):
    """처리 중 응답 (HTTP 200)."""

    status: str = "processing"
    message: str = "YOLO 추론 대기 중"


class WeightInfo(BaseModel):
    """무게 정보."""

    delta: float  # 무게 변화량 (g), 음수 = 제거
    isRemoval: bool  # 상품 제거 여부


class ProcessingStats(BaseModel):
    """처리 통계."""

    topFrames: int
    sideFrames: int
    processingTimeMs: float


class CompleteResponse(BaseModel):
    """완료 응답 (HTTP 200)."""

    status: str = "complete"
    zone: int
    products: List[ProductResponse]
    productCount: int  # 총 상품 개수
    totalPrice: int
    confidence: float
    weightInfo: WeightInfo
    stats: ProcessingStats


# ============================================================================
# Multi-Zone Judge Endpoint
# ============================================================================


@router.post("/multi-zone")
async def judge_multi_zone(
    request: MultiZoneRequest,
    session_store: SessionStore = Depends(get_session_store),
):
    """
    Node.js 폴링용 상품 판단 API.

    데드볼트 문 열리면 10초 간격으로 호출됩니다.
    SessionStore에서 결과를 조회하여:
    - 세션 없음 → "processing" 응답
    - 세션 있음 → "complete" + 상품 정보 응답

    Args:
        request: Multi-Zone 요청 (session_id 필수)
        session_store: SessionStore 의존성

    Returns:
        ProcessingResponse or CompleteResponse
    """
    logger.info(f"[MULTI-ZONE RECEIVED] session_id={request.session_id}")

    # SessionStore에서 결과 조회 (상태 포함)
    session_data, session_status = session_store.get_with_status(request.session_id)

    if session_data is None:
        # 세션이 없거나 만료된 경우
        if session_status == "expired":
            logger.info(
                f"[MULTI-ZONE RESPONSE] session_id={request.session_id}, "
                f"status=processing, reason=expired"
            )
            return {
                "status": "processing",
                "message": "세션이 만료되었습니다. 다시 시도해주세요.",
                "reason": "expired",
            }
        else:
            logger.info(
                f"[MULTI-ZONE RESPONSE] session_id={request.session_id}, "
                f"status=processing, reason=not_found"
            )
            return {
                "status": "processing",
                "message": "YOLO 추론 대기 중",
                "reason": "not_found",
            }

    # 결과가 있으면 complete 응답
    products = [
        {
            "productIdx": p.product_idx if p.product_idx else str(p.product_id),
            "productId": p.product_id,
            "name": p.name,
            "count": p.count,
            "price": p.price,
            "confidence": round(p.confidence, 4),
        }
        for p in session_data.products
    ]

    # 총 상품 개수 계산
    product_count = sum(p.count for p in session_data.products)

    logger.info(
        f"[MULTI-ZONE RESPONSE] session_id={request.session_id}, status=complete, "
        f"zone={session_data.zone}, products={len(products)}, count={product_count}, "
        f"total={session_data.total_price}, delta={session_data.delta_weight:.1f}g"
    )

    return {
        "status": "complete",
        "zone": session_data.zone,
        "products": products,
        "productCount": product_count,
        "totalPrice": session_data.total_price,
        "confidence": round(session_data.confidence, 4),
        "weightInfo": {
            "delta": round(session_data.delta_weight, 1),
            "isRemoval": session_data.delta_weight < 0,
        },
        "stats": {
            "topFrames": session_data.top_frames,
            "sideFrames": session_data.side_frames,
            "processingTimeMs": round(session_data.processing_time_ms, 1),
        },
    }


# ============================================================================
# Session Status Endpoint
# ============================================================================


@router.get("/session/{session_id}")
async def get_session_status(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
):
    """
    세션 상태 조회 (디버깅용).

    Args:
        session_id: 세션 ID

    Returns:
        세션 상세 정보 or 404
    """
    session_data = session_store.get(session_id)

    if session_data is None:
        return {
            "found": False,
            "session_id": session_id,
            "message": "Session not found or expired",
        }

    return {
        "found": True,
        "session_id": session_id,
        "data": session_data.to_dict(),
    }


# ============================================================================
# Session Store Stats Endpoint
# ============================================================================


@router.get("/sessions/stats")
async def get_sessions_stats(
    session_store: SessionStore = Depends(get_session_store),
):
    """
    세션 저장소 통계 조회.

    Returns:
        총 세션 수, 활성 세션 수 등
    """
    return {
        **session_store.get_stats(),
        "timestamp": time.time(),
    }
