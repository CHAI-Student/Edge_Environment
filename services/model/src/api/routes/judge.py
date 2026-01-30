"""
Judge API Routes.

POST /api/judge - 상품 판단 요청
"""

import time
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional

import cv2
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from buffer import FrameBuffer
from vision import YOLOWrapper
from vision.multi_view_ensemble import MultiViewEnsemble
from database.product_db import ProductDatabase
from engine import ProductDecisionEngine, JudgmentStatus
from core.config import config, get_enabled_zones
from api.deps import (
    get_frame_buffer,
    get_yolo,
    get_decision_engine,
    get_product_db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["judge"])


# ============================================================================
# Request/Response Models
# ============================================================================


class WeightData(BaseModel):
    """무게 데이터."""

    delta_weight: float = Field(..., description="무게 변화량 (g)")
    channels: List[int] = Field(default_factory=list, description="변화 감지된 채널")


class JudgeRequest(BaseModel):
    """
    상품 판단 요청 (단순화).

    Node.js에서 /api/frame으로 이미지 전송 후 이 API 호출.
    session_id로 버퍼에서 이미지 조회.
    """

    zone_id: int = Field(..., ge=0, description="Zone ID")
    session_id: str = Field(..., description="세션 ID (프레임 조회용)")
    weight_data: WeightData = Field(..., description="무게 데이터")
    timestamp: Optional[float] = Field(None, description="이벤트 발생 시각")
    vision_only: bool = Field(False, description="Vision 전용 모드")


class ProductJudgment(BaseModel):
    """상품 판단 결과."""

    productId: int
    name: str
    count: int
    unitPrice: int
    totalPrice: int
    confidence: float


class WeightInfo(BaseModel):
    """무게 정보."""

    delta: float
    explained: float
    residual: float


class CameraResult(BaseModel):
    """카메라별 추론 결과."""

    detected: bool = False
    confidence: float = 0.0
    candidates: List[Dict] = Field(default_factory=list)


class JudgeResponse(BaseModel):
    """상품 판단 응답."""

    success: bool
    products: List[ProductJudgment]
    totalPrice: int
    status: str  # complete, partial, uncertain, no_detection
    confidence: float
    weightInfo: WeightInfo
    productCount: int
    isRemoval: bool
    timestamp: float
    camera_results: Optional[Dict[str, CameraResult]] = None


# ============================================================================
# Judge Endpoint
# ============================================================================


@router.post("/judge", response_model=JudgeResponse)
async def judge_products(
    request: JudgeRequest,
    buffer: FrameBuffer = Depends(get_frame_buffer),
    yolo: YOLOWrapper = Depends(get_yolo),
    engine: ProductDecisionEngine = Depends(get_decision_engine),
):
    """
    상품 판단 수행.

    1. FrameBuffer에서 session_id + zone_id로 이미지 조회
    2. YOLO 추론 (top + side)
    3. Multi-View Ensemble
    4. 무게 기반 판단
    5. 결과 반환 및 세션 정리

    Args:
        request: 판단 요청
        buffer: FrameBuffer 의존성
        yolo: YOLOWrapper 의존성
        engine: ProductDecisionEngine 의존성

    Returns:
        JudgeResponse: 판단 결과
    """
    start_time = time.time()
    delta_weight = request.weight_data.delta_weight

    logger.info(
        f"Judge request: zone={request.zone_id}, session={request.session_id}, "
        f"delta_weight={delta_weight:.1f}g, vision_only={request.vision_only}"
    )

    try:
        # 1. 버퍼에서 이미지 조회
        frames = buffer.get_frames(request.session_id, request.zone_id)

        if not frames:
            logger.warning(
                f"No frames found: session={request.session_id}, zone={request.zone_id}"
            )

            # Vision 없이 무게 기반 판단 (fallback)
            if request.vision_only:
                return _create_no_detection_response(delta_weight)

            result = engine.judge_by_weight_only(delta_weight)
            return _convert_judgment_result(result, delta_weight)

        logger.info(f"Found {len(frames)} frames for zone {request.zone_id}")

        # 2. YOLO 추론
        top_detections = []
        side_detections = []
        camera_results = {}

        for camera_id, frame_data in frames.items():
            detections = yolo.detect(frame_data.image)

            # Hand 클래스 필터링
            product_detections = [d for d in detections if not d.is_hand]

            camera_key = f"cam{camera_id}"
            camera_results[camera_key] = CameraResult(
                detected=len(product_detections) > 0,
                confidence=max((d.conf for d in product_detections), default=0.0),
                candidates=[
                    {
                        "class_id": d.cls,
                        "class_name": d.name,
                        "confidence": d.conf,
                    }
                    for d in product_detections[:5]
                ],
            )

            if camera_id == 0:
                top_detections = product_detections
            else:
                side_detections.extend(product_detections)

            logger.debug(
                f"Camera {camera_id}: {len(product_detections)} product detections"
            )

        # 3. Multi-View Ensemble
        ensemble = MultiViewEnsemble()
        vision_candidates = ensemble.combine(
            top_detections=top_detections,
            side_detections=side_detections,
        )

        logger.info(f"Ensemble candidates: {len(vision_candidates)}")

        # 4. 판단 엔진 호출
        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=delta_weight,
            vision_only=request.vision_only,
        )

        # 5. 세션 정리
        buffer.clear_session(request.session_id)

        # 6. 응답 변환
        response = _convert_judgment_result(result, delta_weight, camera_results)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Judgment complete: status={result.status.value}, "
            f"products={len(result.products)}, "
            f"confidence={result.confidence:.3f}, "
            f"elapsed={elapsed_ms:.1f}ms"
        )

        return response

    except Exception as e:
        logger.error(f"Judgment failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Legacy Support: File-based Judge
# ============================================================================


class LegacyJudgeRequest(BaseModel):
    """
    레거시 판단 요청 (파일 경로 기반).

    기존 Node.js 연동 호환을 위해 유지.
    """

    zone_id: int = Field(0, ge=0, description="Zone ID")
    weight_data: Optional[WeightData] = None
    delta_weight: Optional[float] = None
    media_paths: Optional[dict] = None
    vision_only: bool = False
    timestamp: Optional[float] = None


@router.post("/judge/legacy", response_model=JudgeResponse)
async def judge_products_legacy(
    request: LegacyJudgeRequest,
    yolo: YOLOWrapper = Depends(get_yolo),
    engine: ProductDecisionEngine = Depends(get_decision_engine),
):
    """
    레거시 판단 (파일 경로 기반).

    기존 Node.js에서 이미지를 파일로 저장하고 경로를 전달하는 방식.
    점진적 마이그레이션을 위해 유지.
    """
    # delta_weight 결정
    delta_weight = 0.0
    if request.weight_data:
        delta_weight = request.weight_data.delta_weight
    elif request.delta_weight is not None:
        delta_weight = request.delta_weight

    logger.info(
        f"Legacy judge: zone={request.zone_id}, delta={delta_weight:.1f}g, "
        f"vision_only={request.vision_only}"
    )

    # 이미지 경로에서 로드
    top_detections = []
    side_detections = []
    camera_results = {}

    if request.media_paths:
        image_folder = request.media_paths.get("image_folder")

        if image_folder:
            # 프로젝트 루트 기준 경로 해석
            base_dir = Path(__file__).parent.parent.parent.parent.parent
            folder_path = base_dir / image_folder

            if folder_path.exists():
                for img_file in folder_path.glob("*.jpg"):
                    img = cv2.imread(str(img_file))
                    if img is not None:
                        detections = yolo.detect(img)
                        product_dets = [d for d in detections if not d.is_hand]

                        # 파일명으로 카메라 구분
                        if "top" in img_file.stem.lower():
                            top_detections.extend(product_dets)
                            camera_results["cam0"] = CameraResult(
                                detected=len(product_dets) > 0,
                                confidence=max((d.conf for d in product_dets), default=0.0),
                                candidates=[{"class_id": d.cls, "class_name": d.name, "confidence": d.conf} for d in product_dets[:5]],
                            )
                        else:
                            side_detections.extend(product_dets)

    # Ensemble
    ensemble = MultiViewEnsemble()
    vision_candidates = ensemble.combine(top_detections, side_detections)

    # 판단
    result = engine.judge(
        vision_candidates=vision_candidates,
        delta_weight=delta_weight,
        vision_only=request.vision_only,
    )

    return _convert_judgment_result(result, delta_weight, camera_results)


# ============================================================================
# Helper Functions
# ============================================================================


def _convert_judgment_result(
    result,
    delta_weight: float,
    camera_results: Optional[Dict[str, CameraResult]] = None,
) -> JudgeResponse:
    """JudgmentResult를 JudgeResponse로 변환."""
    products = [
        ProductJudgment(
            productId=p.product_id,
            name=p.name,
            count=p.count,
            unitPrice=p.unit_price,
            totalPrice=p.total_price,
            confidence=p.confidence,
        )
        for p in result.products
    ]

    return JudgeResponse(
        success=True,
        products=products,
        totalPrice=result.total_price,
        status=result.status.value,
        confidence=result.confidence,
        weightInfo=WeightInfo(
            delta=result.weight_delta,
            explained=result.weight_explained,
            residual=result.weight_residual,
        ),
        productCount=sum(p.count for p in products),
        isRemoval=delta_weight < 0,
        timestamp=result.timestamp,
        camera_results=camera_results,
    )


def _create_no_detection_response(delta_weight: float) -> JudgeResponse:
    """NO_DETECTION 응답 생성."""
    return JudgeResponse(
        success=True,
        products=[],
        totalPrice=0,
        status="no_detection",
        confidence=0.0,
        weightInfo=WeightInfo(
            delta=delta_weight,
            explained=0.0,
            residual=abs(delta_weight),
        ),
        productCount=0,
        isRemoval=delta_weight < 0,
        timestamp=time.time(),
        camera_results=None,
    )


# ============================================================================
# Zone Config
# ============================================================================


@router.get("/zones/config")
async def get_zones_config():
    """
    Zone 설정 조회.

    Returns:
        활성화된 zone 정보
    """
    from core.config import ZONE_CHANNEL_MAP, ZONE_CAMERA_MAP, TOP_CAMERA_ID

    return {
        "enabled_zones": get_enabled_zones(),
        "zone_channel_map": dict(ZONE_CHANNEL_MAP),
        "zone_camera_map": dict(ZONE_CAMERA_MAP),
        "top_camera_id": TOP_CAMERA_ID,
        "timestamp": time.time(),
    }
