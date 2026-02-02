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
from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from session import SessionStore, SessionData, ProductResult, DoorSessionStore
from engine import ProductDecisionEngine, EnsembleResult
from database.product_db import ProductDatabase
from api.deps import get_session_store, get_product_db, get_decision_engine, get_door_session_store_optional

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

    session_id: Optional[str] = Field(default=None, description="세션 ID (선택)")
    products: List[ProductInfo] = Field(
        default_factory=list,
        description="상품 목록 (선택, 무게 검증용)",
    )
    zone: Optional[int] = Field(default=None, description="Zone 번호 (세션 필터용)")


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
# Request Parsing Helper
# ============================================================================


def _parse_request(body: Any) -> MultiZoneRequest:
    """
    유연한 요청 파싱.

    Node.js가 보내는 배열 형식과 기존 객체 형식 모두 처리:
    - 배열: Node.js가 productData 직접 전송 (session_id 없음)
    - 객체: 기존 형식 {session_id?, products, zone?}

    Args:
        body: 요청 본문 (list 또는 dict)

    Returns:
        MultiZoneRequest
    """
    if isinstance(body, list):
        # Node.js 배열 형식: productData 직접 전송
        products = []
        for p in body:
            try:
                products.append(ProductInfo(**p))
            except Exception as e:
                logger.warning(f"[PARSE] Invalid product item: {p}, error: {e}")
        return MultiZoneRequest(products=products)

    elif isinstance(body, dict):
        # 기존 객체 형식
        products = []
        for p in body.get("products", []):
            try:
                products.append(ProductInfo(**p))
            except Exception as e:
                logger.warning(f"[PARSE] Invalid product item: {p}, error: {e}")
        return MultiZoneRequest(
            session_id=body.get("session_id"),
            products=products,
            zone=body.get("zone"),
        )

    raise ValueError(f"Invalid request format: expected list or dict, got {type(body)}")


# ============================================================================
# Multi-Zone Judge Endpoint
# ============================================================================


@router.post("/multi-zone")
async def judge_multi_zone(
    body: Any = Body(...),
    session_store: SessionStore = Depends(get_session_store),
    product_db: ProductDatabase = Depends(get_product_db),
    engine: ProductDecisionEngine = Depends(get_decision_engine),
    door_session_store: DoorSessionStore | None = Depends(get_door_session_store_optional),
):
    """
    Node.js 폴링용 상품 판단 API.

    데드볼트 문 열리면 10초 간격으로 호출됩니다.
    SessionStore에서 결과를 조회하여:
    - 세션 없음 → "processing" 응답 (success=false)
    - 세션 있음 → "complete" + 상품 정보 응답 (success=true)

    지원하는 요청 형식:
    1. 배열 직접 전송: [{"product_idx": "26", ...}, ...]
    2. 객체 형식: {"session_id": "...", "products": [...], "zone": 1}

    session_id가 없으면 최근 활성 세션을 자동으로 선택합니다.

    Args:
        body: 요청 본문 (list 또는 dict)
        session_store: SessionStore 의존성

    Returns:
        ProcessingResponse or CompleteResponse (모두 success 필드 포함)
    """
    # 요청 파싱
    logger.info(f"[MULTI-ZONE REQUEST] body_type={type(body).__name__}")

    try:
        request = _parse_request(body)
    except ValueError as e:
        logger.error(f"[MULTI-ZONE ERROR] Failed to parse request: {e}")
        return {
            "success": False,
            "status": "error",
            "message": str(e),
            "reason": "parse_error",
        }

    logger.info(
        f"[MULTI-ZONE PARSED] session_id={request.session_id}, "
        f"products={len(request.products)}, zone={request.zone}"
    )

    # Door Session 기반 응답 (v4.1) - DoorSessionStore가 활성화되어 있으면 우선 사용
    if door_session_store is not None and request.zone is not None:
        door_session, is_finalized = door_session_store.get_or_finalize(request.zone)

        if door_session is not None:
            # DoorSession 기반 응답 생성
            active_products = door_session.get_active_products()

            # 상품 정보 변환
            products_response = [
                {
                    "productIdx": p.product_idx if p.product_idx else str(p.product_id),
                    "productId": p.product_id,
                    "name": p.name,
                    "count": p.count,
                    "price": p.unit_price,
                    "confidence": round(p.average_confidence, 4),
                }
                for p in active_products
            ]

            # 총 상품 개수 및 금액
            product_count = sum(p.count for p in active_products)
            total_price = door_session.total_price

            # device_id 추출
            is_valid_session_id = (
                request.session_id is not None
                and request.session_id.startswith("zone_")
            )
            device_id = None if is_valid_session_id else request.session_id

            if is_finalized:
                # 세션 종료 (complete)
                logger.info(
                    f"[MULTI-ZONE DOOR SESSION COMPLETE] "
                    f"door_session_id={door_session.door_session_id}, "
                    f"triggers={door_session.trigger_count}, "
                    f"products={product_count}, total_price={total_price}"
                )

                # unmatched_returns 정보 (v4.2)
                unmatched_info = None
                if door_session.has_unmatched_returns:
                    unmatched_info = {
                        "count": len(door_session.unmatched_returns),
                        "totalWeight": round(door_session.unmatched_returns_weight, 1),
                        "details": [
                            {
                                "triggerId": r.trigger_id,
                                "deltaWeight": round(r.delta_weight, 1),
                                "timestamp": r.timestamp,
                            }
                            for r in door_session.unmatched_returns
                        ],
                    }

                return {
                    "success": product_count > 0,
                    "status": "complete",
                    "device_id": device_id,
                    "zone": door_session.zone,
                    "door_session_id": door_session.door_session_id,
                    "session_id": door_session.triggers[-1].session_id if door_session.triggers else None,
                    "processing_stage": "complete",
                    "processing_stage_detail": f"Door session 완료: {door_session.trigger_count}개 trigger 통합",
                    "products": products_response,
                    "productCount": product_count,
                    "totalPrice": total_price,
                    "confidence": round(
                        sum(p.average_confidence for p in active_products) / len(active_products)
                        if active_products else 0.0,
                        4,
                    ),
                    "weightInfo": {
                        "delta": round(
                            sum(t.delta_weight for t in door_session.triggers),
                            1,
                        ),
                        "isRemoval": sum(t.delta_weight for t in door_session.triggers) < 0,
                    },
                    "doorSessionInfo": {
                        "triggerCount": door_session.trigger_count,
                        "durationSeconds": round(door_session.duration_seconds, 1),
                        "createdAt": door_session.created_at,
                        "finalizedAt": door_session.finalized_at,
                        "unmatchedReturns": unmatched_info,
                    },
                    "stats": {
                        "topFrames": 0,
                        "sideFrames": 0,
                        "processingTimeMs": round(
                            sum(t.processing_time_ms for t in door_session.triggers),
                            1,
                        ),
                    },
                }
            else:
                # 세션 진행 중 (in_progress)
                logger.info(
                    f"[MULTI-ZONE DOOR SESSION IN_PROGRESS] "
                    f"door_session_id={door_session.door_session_id}, "
                    f"triggers={door_session.trigger_count}, "
                    f"interim_products={product_count}"
                )
                return {
                    "success": False,
                    "status": "in_progress",
                    "device_id": device_id,
                    "zone": door_session.zone,
                    "door_session_id": door_session.door_session_id,
                    "session_id": door_session.triggers[-1].session_id if door_session.triggers else None,
                    "processing_stage": "door_session_active",
                    "processing_stage_detail": f"Door session 활성: {door_session.trigger_count}개 trigger 수신",
                    "interim_products": products_response,
                    "interimProductCount": product_count,
                    "interimTotalPrice": total_price,
                    "doorSessionInfo": {
                        "triggerCount": door_session.trigger_count,
                        "durationSeconds": round(door_session.duration_seconds, 1),
                        "createdAt": door_session.created_at,
                        "lastTriggerAt": door_session.last_trigger_at,
                    },
                    "stats": {
                        "topFrames": 0,
                        "sideFrames": 0,
                        "processingTimeMs": round(
                            sum(t.processing_time_ms for t in door_session.triggers),
                            1,
                        ),
                    },
                }

    # 기존 SessionStore 기반 응답 (DoorSession이 없거나 비활성화된 경우)
    # session_id 유효성 검사: zone_으로 시작하면 실제 세션 ID, 아니면 device_id
    # Node.js가 deviceIdx(예: "DE17683631997086480")를 session_id로 보내는 경우
    is_valid_session_id = (
        request.session_id is not None
        and request.session_id.startswith("zone_")
    )

    # device_id 추출: zone_으로 시작 안하면 device_id로 간주
    device_id = None if is_valid_session_id else request.session_id

    if is_valid_session_id:
        # 유효한 session_id로 조회
        session_data, session_status = session_store.get_with_status(request.session_id)
    else:
        # device_id이거나 없으면 최근 활성 세션 자동 선택
        if device_id:
            logger.info(
                f"[MULTI-ZONE] device_id={device_id}, "
                f"looking up latest active session for zone={request.zone}"
            )
        session_data = session_store.get_latest_active(request.zone)
        session_status = "found" if session_data else "no_active_session"

    if session_data is None:
        # 세션이 없거나 만료된 경우
        if session_status == "expired":
            logger.info(
                f"[MULTI-ZONE RESPONSE] device_id={device_id}, session_id={request.session_id}, "
                f"status=processing, reason=expired"
            )
            return {
                "success": False,
                "status": "processing",
                "message": "세션이 만료되었습니다. 다시 시도해주세요.",
                "reason": "expired",
                "device_id": device_id,
                "processing_stage": "expired",
                "processing_stage_detail": "세션 TTL 만료",
            }
        elif session_status == "no_active_session":
            logger.info(
                f"[MULTI-ZONE RESPONSE] device_id={device_id}, zone={request.zone}, "
                f"status=processing, reason=no_active_session"
            )
            return {
                "success": False,
                "status": "processing",
                "message": "활성 세션이 없습니다",
                "reason": "no_active_session",
                "device_id": device_id,
                "processing_stage": "waiting",
                "processing_stage_detail": "카메라 트리거 대기 중",
            }
        else:
            logger.info(
                f"[MULTI-ZONE RESPONSE] device_id={device_id}, session_id={request.session_id}, "
                f"status=processing, reason=not_found"
            )
            return {
                "success": False,
                "status": "processing",
                "message": "YOLO 추론 대기 중",
                "reason": "not_found",
                "device_id": device_id,
                "processing_stage": "waiting",
                "processing_stage_detail": "세션 생성 대기 중",
            }

    # 세션이 아직 처리 중인 경우 (status="processing")
    if session_data.status == "processing":
        logger.info(
            f"[MULTI-ZONE RESPONSE] device_id={device_id}, session_id={session_data.session_id}, "
            f"status=processing, stage={session_data.processing_stage}"
        )
        return {
            "success": False,
            "status": "processing",
            "message": session_data.processing_stage_detail or "처리 중",
            "reason": "in_progress",
            "device_id": device_id,
            "session_id": session_data.session_id,
            "zone": session_data.zone,
            "processing_stage": session_data.processing_stage,
            "processing_stage_detail": session_data.processing_stage_detail,
        }

    # Node.js에서 전달한 product_weight로 무게 업데이트 + 재계산
    if request.products and session_data.vision_candidates:
        weights_updated = False
        updated_product_ids = []

        for p in request.products:
            try:
                weight = float(p.product_weight) if p.product_weight else 0.0
            except (ValueError, TypeError):
                weight = 0.0

            if weight > 0:
                # product_idx로 YOLO class_id 조회
                class_id = product_db.get_yolo_class_id_by_product_idx(p.product_idx)
                if class_id is not None:
                    old_weight = product_db.get_weight(class_id)
                    if old_weight != weight:
                        product_db.update_weight(class_id, weight)
                        weights_updated = True
                        updated_product_ids.append(class_id)
                        logger.info(
                            f"[MULTI-ZONE] Weight updated: product_idx={p.product_idx}, "
                            f"class_id={class_id}, {old_weight}g -> {weight}g"
                        )

        # 무게가 업데이트되었으면 개수 재계산
        if weights_updated and session_data.status == "complete":
            logger.info(
                f"[MULTI-ZONE] Recalculating counts with updated weights: "
                f"updated_ids={updated_product_ids}"
            )

            # vision_candidates를 EnsembleResult로 복원
            vision_candidates = [
                EnsembleResult(
                    class_id=vc["class_id"],
                    class_name=vc["class_name"],
                    top_confidence=vc.get("top_confidence", 0.0),
                    side_confidence=vc.get("side_confidence", 0.0),
                    combined_confidence=vc.get("combined_confidence", 0.0),
                    vote_count=vc.get("vote_count", 1),
                )
                for vc in session_data.vision_candidates
            ]

            # 재판단
            result = engine.judge(
                vision_candidates=vision_candidates,
                delta_weight=session_data.delta_weight,
                vision_only=False,
            )

            # 세션 데이터 업데이트
            def get_product_idx(product_id: int) -> Optional[str]:
                """YOLO class_id로 IF11 product_idx 조회."""
                product_info = product_db.get_by_yolo_class_id(product_id)
                if product_info and product_info.product_idx:
                    return product_info.product_idx
                return None

            new_products = [
                ProductResult(
                    product_id=p.product_id,
                    product_idx=get_product_idx(p.product_id),
                    name=p.name,
                    count=p.count,
                    price=p.unit_price,
                    confidence=p.confidence,
                )
                for p in result.products
            ]

            # 세션 업데이트
            session_data.products = new_products
            session_data.total_price = result.total_price
            session_data.confidence = result.confidence
            session_data.processing_stage_detail = f"무게 보정 후 재계산: 상품 {len(new_products)}개"

            # 세션 저장소에 저장
            session_store.save(session_data.session_id, session_data)

            logger.info(
                f"[MULTI-ZONE] Recalculation complete: "
                f"products={len(new_products)}, total_price={result.total_price}"
            )

    # 결과가 있으면 complete 응답
    # 개수가 0인 상품은 제외 (Node.js에서 요청한 상품 목록에 포함되지 않음)
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
        if p.count > 0  # 개수 0인 상품 필터링
    ]

    # 총 상품 개수 계산 (count > 0인 상품만)
    product_count = sum(p.count for p in session_data.products if p.count > 0)

    # success 조건: status가 "complete"이고 개수가 0보다 큰 상품이 하나 이상 있을 때만 true
    is_success = session_data.status == "complete" and product_count > 0

    logger.info(
        f"[MULTI-ZONE RESPONSE] device_id={device_id}, session_id={session_data.session_id}, "
        f"status=complete, zone={session_data.zone}, products={len(products)}, "
        f"count={product_count}, total={session_data.total_price}, delta={session_data.delta_weight:.1f}g, "
        f"success={is_success}"
    )

    return {
        "success": is_success,
        "status": "complete",
        "device_id": device_id,
        "zone": session_data.zone,
        "session_id": session_data.session_id,
        "processing_stage": session_data.processing_stage,
        "processing_stage_detail": session_data.processing_stage_detail,
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
    door_session_store: DoorSessionStore | None = Depends(get_door_session_store_optional),
):
    """
    세션 저장소 통계 조회.

    Returns:
        총 세션 수, 활성 세션 수 등
    """
    result = {
        **session_store.get_stats(),
        "timestamp": time.time(),
    }

    if door_session_store is not None:
        result["door_session_store"] = door_session_store.get_stats()

    return result


# ============================================================================
# Door Session Endpoints (v4.1)
# ============================================================================


@router.get("/door-sessions/stats")
async def get_door_sessions_stats(
    door_session_store: DoorSessionStore | None = Depends(get_door_session_store_optional),
):
    """
    Door Session 저장소 통계 조회.

    Returns:
        활성 Door Session 수, YAML 저장 현황 등
    """
    if door_session_store is None:
        return {
            "enabled": False,
            "message": "DoorSessionStore is not enabled",
        }

    return {
        "enabled": True,
        **door_session_store.get_stats(),
        "timestamp": time.time(),
    }


@router.get("/door-session/{zone}")
async def get_door_session_status(
    zone: int,
    door_session_store: DoorSessionStore | None = Depends(get_door_session_store_optional),
):
    """
    특정 Zone의 Door Session 상태 조회.

    Args:
        zone: Zone 번호

    Returns:
        Door Session 상세 정보 or 404
    """
    if door_session_store is None:
        return {
            "found": False,
            "zone": zone,
            "message": "DoorSessionStore is not enabled",
        }

    door_session = door_session_store.get_session(zone)

    if door_session is None:
        return {
            "found": False,
            "zone": zone,
            "message": "No active door session for this zone",
        }

    return {
        "found": True,
        "zone": zone,
        "data": door_session.to_dict(),
    }


@router.post("/door-session/{zone}/finalize")
async def finalize_door_session(
    zone: int,
    door_session_store: DoorSessionStore | None = Depends(get_door_session_store_optional),
):
    """
    Door Session 강제 종료.

    Args:
        zone: Zone 번호

    Returns:
        종료된 Door Session 정보
    """
    if door_session_store is None:
        return {
            "success": False,
            "zone": zone,
            "message": "DoorSessionStore is not enabled",
        }

    door_session = door_session_store.finalize_session(zone)

    if door_session is None:
        return {
            "success": False,
            "zone": zone,
            "message": "No active door session to finalize",
        }

    return {
        "success": True,
        "zone": zone,
        "door_session_id": door_session.door_session_id,
        "trigger_count": door_session.trigger_count,
        "product_count": door_session.product_count,
        "total_price": door_session.total_price,
        "message": "Door session finalized successfully",
    }
