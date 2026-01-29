"""
API Routes for Model Service.

REST API 엔드포인트 정의.

엔드포인트:
- GET /api/health: 헬스 체크
- POST /api/judge: 상품 판단 요청 (Node.js에서 호출)
- GET /api/products: 상품 목록
- POST /api/judge/multi-zone: 다중 Zone 동시 판단
- POST /api/judge/with-history: 히스토리 기반 판단 (반환/연속픽업)
- GET /api/stats/recognition-rate: 인식률 통계
"""

from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
import logging
import time
import os
import shutil
import asyncio
import uuid
from pathlib import Path

from ..config import config, get_enabled_zones, get_zone_count, is_zone_enabled
from ..database.product_db import ProductDatabase
from ..engine import ProductDecisionEngine, EnsembleResult, JudgmentStatus
from ..engine.event_tracker import EventTracker, EventDirection
from ..engine.advanced import (
    ReturnDetector,
    CrossZoneDetector,
    BaselineManager,
    RapidPickupHandler,
)
from ..weight import MultiZoneWeightMonitor, RecordingProcessor, convert_to_weight_data

from .models import (
    # Multi-Zone
    MultiZoneJudgeRequest,
    MultiZoneJudgeResponse,
    ZoneJudgmentResult,
    CrossZoneMovementResult,
    JudgmentStatusEnum,
    # History
    HistoryJudgeRequest,
    HistoryJudgeResponse,
    ReturnDetectionResult,
    RapidPickupResult as RapidPickupResultModel,
    # Stats
    RecognitionRateResponse,
    ZoneStatistics,
    # Product Registration
    ProductRegisterRequest,
    ProductRegisterResponse,
    ProductUpdateRequest,
    ProductUpdateResponse,
    ProductDeleteResponse,
    ImageUploadResponse,
    ProductExportResponse,
    ProductSearchRequest,
    # Lightweight Model (Node.js Integration)
    WeightData,
    MediaPaths,
    JudgmentMetadata,
    NewJudgeRequest,
    NewJudgeResponse,
    # Recording Data Processing
    RecordingData,
    RecordingProcessRequest,
    RecordingProcessResponse,
)

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
    """
    상품 판단 요청.

    지원 형식:
    1. weight_data (권장): before_weights, after_weights, delta_weight, channels
    2. recording (새로운 형식): IO Board에서 recording된 시리얼 데이터
    3. loadcell_weights + baseline_weights (레거시): 단일 시점 무게 비교
    """
    # 새로운 형식 (권장)
    weight_data: Optional[WeightData] = None
    media_paths: Optional[MediaPaths] = None

    # Recording 형식 (IO Board 시리얼 데이터)
    recording: Optional[RecordingData] = None

    # 레거시 형식 (deprecated)
    snapshot_folder: Optional[str] = None
    loadcell_weights: List[str] = Field(default_factory=list)
    baseline_weights: List[str] = Field(default_factory=list)

    # 공통 필드
    zone_id: int = 0
    products: List[ProductItem] = Field(default_factory=list)
    delta_weight: Optional[float] = None  # 직접 무게 변화량 지정
    vision_candidates: Optional[List[dict]] = None  # 직접 Vision 후보군 지정
    timestamp: Optional[float] = None  # 이벤트 타임스탬프
    inference_id: Optional[str] = None  # 추론 ID (취소용)
    vision_only: bool = False  # Vision 전용 모드 (로드셀 없이 카메라만 사용)


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
    status: str  # complete, partial, uncertain, no_detection, cancelled
    confidence: float
    weightInfo: WeightInfoResponse
    productCount: int
    isRemoval: bool
    timestamp: float
    inference_id: Optional[str] = None  # 추론 ID
    camera_results: Optional[Dict] = None  # 카메라별 Vision 결과


class ModelHealthResponse(BaseModel):
    """헬스 체크 응답 (IO Board 형식 호환)."""
    model: str  # "HEALTHY" | "UNHEALTHY"


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

# Advanced modules (고급 기능)
_event_tracker: Optional[EventTracker] = None
_return_detector: Optional[ReturnDetector] = None
_cross_zone_detector: Optional[CrossZoneDetector] = None
_baseline_manager: Optional[BaselineManager] = None
_rapid_pickup_handler: Optional[RapidPickupHandler] = None
_multi_zone_monitor: Optional[MultiZoneWeightMonitor] = None

# Statistics counters
_stats: Dict[str, int] = {
    "total_events": 0,
    "successful_judgments": 0,
    "failed_judgments": 0,
    "return_events": 0,
    "cross_zone_moves": 0,
}
# Zone별 통계 (활성화된 zone 기반으로 초기화)
_zone_stats: Dict[int, Dict[str, int]] = {}


def _init_zone_stats():
    """활성화된 zone 기반으로 통계 초기화."""
    global _zone_stats
    _zone_stats = {
        zone_id: {
            "total_events": 0,
            "successful_judgments": 0,
            "failed_judgments": 0,
            "return_events": 0,
            "cross_zone_moves": 0,
        }
        for zone_id in get_enabled_zones()
    }


# 모듈 로드 시 초기화
_init_zone_stats()

# Active inferences tracking (for cancellation support)
# Format: {inference_id: (cancel_event, created_timestamp)}
MAX_ACTIVE_INFERENCES = 100  # 최대 동시 추론 수
INFERENCE_TTL_SECONDS = 300  # 추론 TTL (5분)
_active_inferences: Dict[str, tuple] = {}  # {id: (Event, timestamp)}
_inference_lock = asyncio.Lock()


def init_routes(product_db: ProductDatabase, decision_engine: ProductDecisionEngine):
    """라우터 초기화 (main.py에서 호출)."""
    global _product_db, _decision_engine
    global _event_tracker, _return_detector, _cross_zone_detector
    global _baseline_manager, _rapid_pickup_handler, _multi_zone_monitor

    _product_db = product_db
    _decision_engine = decision_engine

    # Zone 통계 재초기화 (설정 변경 대응)
    _init_zone_stats()

    # 활성화된 zone 개수 가져오기
    zone_count = get_zone_count()

    # Initialize advanced modules
    _event_tracker = EventTracker(max_history=100)
    _return_detector = ReturnDetector(return_window=60.0)
    _cross_zone_detector = CrossZoneDetector()
    _baseline_manager = BaselineManager(drift_rate=0.5, zone_count=zone_count)
    _rapid_pickup_handler = RapidPickupHandler(buffer_window=3.0)
    _multi_zone_monitor = MultiZoneWeightMonitor(zone_count=zone_count)

    enabled_zones = get_enabled_zones()
    logger.info(f"API routes initialized with {zone_count} zones: {enabled_zones}")


@router.get("/health", response_model=ModelHealthResponse)
async def health_check():
    """헬스 체크 - 모델 파일 존재 여부 확인."""
    model_path = config.yolo_model_path

    # 상대 경로인 경우 절대 경로로 변환
    if not os.path.isabs(model_path):
        # services/model 디렉토리 기준
        base_dir = Path(__file__).parent.parent
        model_path = str(base_dir / model_path)

    # 모델 파일 존재 여부 확인
    model_exists = os.path.exists(model_path)

    return ModelHealthResponse(
        model="HEALTHY" if model_exists else "UNHEALTHY",
    )


@router.get("/zones/config")
async def get_zones_config():
    """
    현재 Zone 설정 조회.

    활성화된 zone 목록과 채널/카메라 매핑 정보를 반환합니다.
    ENABLED_ZONE_COUNT 환경변수로 zone 개수를 조절할 수 있습니다.

    Returns:
        Zone 설정 정보
    """
    from ..config import ZONE_CHANNEL_MAP, ZONE_CAMERA_MAP, ZONE_CONFIG, TOP_CAMERA_ID

    return {
        "enabled_zones": get_enabled_zones(),
        "zone_count": get_zone_count(),
        "zone_channel_map": dict(ZONE_CHANNEL_MAP),
        "zone_camera_map": dict(ZONE_CAMERA_MAP),
        "zone_config": dict(ZONE_CONFIG),
        "top_camera_id": TOP_CAMERA_ID,
        "timestamp": time.time(),
    }


# ===== Inference Cancellation =====

class InferenceCancelRequest(BaseModel):
    """추론 취소 요청."""
    inference_id: str


class InferenceCancelResponse(BaseModel):
    """추론 취소 응답."""
    cancelled: bool
    inference_id: str
    reason: Optional[str] = None


@router.post("/judge/cancel", response_model=InferenceCancelResponse)
async def cancel_inference(request: InferenceCancelRequest):
    """
    진행 중인 추론 취소.

    Node.js에서 새로운 무게 이벤트 발생 시 기존 추론을 중단하기 위해 호출합니다.

    Args:
        request: 취소 요청 (inference_id)

    Returns:
        InferenceCancelResponse: 취소 결과
    """
    global _active_inferences

    inference_id = request.inference_id

    async with _inference_lock:
        if inference_id not in _active_inferences:
            return InferenceCancelResponse(
                cancelled=False,
                inference_id=inference_id,
                reason="not_found",
            )

        # 취소 이벤트 설정 (tuple의 첫 번째 요소가 Event)
        cancel_event, _ = _active_inferences[inference_id]
        cancel_event.set()

        logger.info(f"Inference cancelled: {inference_id}")

        return InferenceCancelResponse(
            cancelled=True,
            inference_id=inference_id,
        )


@router.get("/judge/active")
async def get_active_inferences():
    """
    진행 중인 추론 목록 조회.

    Returns:
        활성 추론 ID 목록
    """
    global _active_inferences

    async with _inference_lock:
        return {
            "active_inferences": list(_active_inferences.keys()),
            "count": len(_active_inferences),
            "timestamp": time.time(),
        }


async def _cleanup_stale_inferences():
    """TTL 초과된 추론 정리."""
    global _active_inferences
    current_time = time.time()
    stale_ids = [
        inf_id for inf_id, (_, created_at) in _active_inferences.items()
        if current_time - created_at > INFERENCE_TTL_SECONDS
    ]
    for inf_id in stale_ids:
        logger.warning(f"Cleaning up stale inference: {inf_id}")
        del _active_inferences[inf_id]
    return len(stale_ids)


async def _register_inference(inference_id: str) -> asyncio.Event:
    """추론 등록 및 취소 이벤트 생성."""
    global _active_inferences

    async with _inference_lock:
        # 먼저 TTL 초과된 추론 정리
        await _cleanup_stale_inferences()

        # 최대 개수 초과 시 가장 오래된 것 제거
        if len(_active_inferences) >= MAX_ACTIVE_INFERENCES:
            oldest_id = min(_active_inferences.keys(),
                          key=lambda k: _active_inferences[k][1])
            logger.warning(f"Max inferences reached, removing oldest: {oldest_id}")
            del _active_inferences[oldest_id]

        cancel_event = asyncio.Event()
        _active_inferences[inference_id] = (cancel_event, time.time())
        return cancel_event


async def _unregister_inference(inference_id: str):
    """추론 등록 해제."""
    global _active_inferences

    async with _inference_lock:
        if inference_id in _active_inferences:
            del _active_inferences[inference_id]


@router.post("/judge", response_model=JudgeResponse)
async def judge_products(request: JudgeRequest):
    """
    상품 판단 수행.

    Node.js Orchestrator에서 호출하여 상품을 판단합니다.

    새로운 형식 (권장):
        {
            "zone_id": 0,
            "weight_data": {"before_weights": [...], "after_weights": [...], "delta_weight": -520, "channels": [0, 1]},
            "media_paths": {"image_folder": "/data/snapshots/...", "top_image": "...", "side_image": "..."},
            "timestamp": 1737897025.123,
            "inference_id": "inf_123456789"
        }

    레거시 형식 (하위 호환):
        {
            "loadcell_weights": ["+00480", ...],
            "baseline_weights": ["+01000", ...],
            "zone_id": 0
        }

    Args:
        request: 판단 요청

    Returns:
        JudgeResponse: 판단 결과
    """
    global _product_db, _decision_engine

    if _decision_engine is None:
        raise HTTPException(status_code=503, detail="Decision engine not initialized")

    # inference_id 생성 또는 사용
    inference_id = request.inference_id or f"inf_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"

    # 추론 등록
    cancel_event = await _register_inference(inference_id)

    start_time = time.time()
    images_processed = []
    camera_results = {}  # 카메라별 Vision 결과

    logger.info(f"Judge request: zone_id={request.zone_id}, inference_id={inference_id}")

    try:
        # 취소 체크
        if cancel_event.is_set():
            return JudgeResponse(
                success=False,
                products=[],
                totalPrice=0,
                status="cancelled",
                confidence=0.0,
                weightInfo=WeightInfoResponse(delta=0, explained=0, residual=0),
                productCount=0,
                isRemoval=False,
                timestamp=time.time(),
                inference_id=inference_id,
            )

        # Vision 전용 모드 체크
        vision_only = request.vision_only

        # media_paths만 있고 weight_data가 없으면 자동으로 vision_only 모드
        if request.media_paths is not None and request.weight_data is None and request.delta_weight is None:
            if not request.loadcell_weights:
                vision_only = True
                logger.info("Auto-enabled vision_only mode (no weight data provided)")

        # 1. 무게 변화량 결정 (새 형식 우선)
        if vision_only:
            # Vision 전용 모드: 무게 데이터 불필요
            delta_weight = 0.0
            logger.info(f"Vision-only mode: zone={request.zone_id}, no weight data required")
        elif request.weight_data is not None:
            # 새로운 형식: weight_data에서 delta_weight 사용
            delta_weight = request.weight_data.delta_weight
            logger.info(f"Using weight_data: delta={delta_weight:.1f}g, channels={request.weight_data.channels}")
        elif request.recording is not None:
            # Recording 형식: IO Board 시리얼 데이터에서 계산
            recording_processor = RecordingProcessor()
            recording_logs = [
                {"loadcells": log.loadcells, "timestamp": log.timestamp}
                for log in request.recording.logs
            ]
            processed = recording_processor.process(
                recording_logs=recording_logs,
                zone_id=request.recording.zone_id,
                zone_channels=request.recording.zone_channels,
            )
            delta_weight = processed.delta_weight
            logger.info(
                f"Using recording data: zone={request.recording.zone_id}, "
                f"samples={processed.sample_count}, delta={delta_weight:.1f}g, "
                f"channels={processed.channels}"
            )
        elif request.delta_weight is not None:
            # 직접 지정된 delta_weight
            delta_weight = request.delta_weight
        else:
            # 레거시 형식: loadcell_weights에서 계산
            delta_weight = _calculate_delta_weight(
                request.loadcell_weights,
                request.baseline_weights,
                request.zone_id,
            )

        logger.info(f"Zone {request.zone_id} delta_weight: {delta_weight:.1f}g, vision_only={vision_only}")

        # 취소 체크 (Vision 처리 전)
        if cancel_event.is_set():
            return JudgeResponse(
                success=False,
                products=[],
                totalPrice=0,
                status="cancelled",
                confidence=0.0,
                weightInfo=WeightInfoResponse(delta=delta_weight, explained=0, residual=delta_weight),
                productCount=0,
                isRemoval=delta_weight < 0,
                timestamp=time.time(),
                inference_id=inference_id,
            )

        # 2. Vision 후보군 생성
        vision_candidates = []

        if request.vision_candidates:
            # 직접 제공된 Vision 후보군 사용
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
            logger.info(f"Using {len(vision_candidates)} provided vision candidates")

        elif request.media_paths is not None:
            # 이미지 경로에서 Vision 추론 수행
            vision_candidates, images_processed, camera_results = await _run_vision_from_media_paths(
                request.media_paths,
                request.zone_id,
            )
            logger.info(f"Vision inference from files: {len(vision_candidates)} candidates, {len(images_processed)} images, {len(camera_results)} cameras")

        elif request.snapshot_folder:
            # 레거시: snapshot_folder에서 이미지 로드
            media_paths = MediaPaths(image_folder=request.snapshot_folder)
            vision_candidates, images_processed, camera_results = await _run_vision_from_media_paths(
                media_paths,
                request.zone_id,
            )
            logger.info(f"Vision inference from snapshot_folder: {len(vision_candidates)} candidates")

        else:
            logger.warning("No vision candidates or image paths provided, using empty list")

        # 취소 체크 (Vision 처리 후, Decision Engine 전)
        if cancel_event.is_set():
            return JudgeResponse(
                success=False,
                products=[],
                totalPrice=0,
                status="cancelled",
                confidence=0.0,
                weightInfo=WeightInfoResponse(delta=delta_weight, explained=0, residual=delta_weight),
                productCount=0,
                isRemoval=delta_weight < 0,
                timestamp=time.time(),
                inference_id=inference_id,
            )

        # 3. 판단 수행
        result = _decision_engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=delta_weight,
            vision_only=vision_only,
        )

        # 4. 처리 시간 계산
        processing_time_ms = (time.time() - start_time) * 1000

        # 5. 응답 변환
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
            timestamp=request.timestamp or result.timestamp,
            inference_id=inference_id,
            camera_results=camera_results if camera_results else None,
        )

        logger.info(
            f"Judge result: status={result.status.value}, "
            f"products={len(result.products)}, totalPrice={result.total_price}, "
            f"processing_time={processing_time_ms:.1f}ms, inference_id={inference_id}"
        )

        # 6. 성공적인 픽업 이벤트 기록 (반환 감지용)
        if result.is_success and result.products and delta_weight < 0 and _return_detector:
            for p in result.products:
                _return_detector.record_pickup(
                    zone_id=request.zone_id,
                    weight=abs(delta_weight),
                    product_id=p.product_id,
                    product_name=p.name,
                    count=p.count,
                )
            logger.debug(f"Recorded {len(result.products)} pickup events for return detection")

        return response

    except Exception as e:
        logger.error(f"Judge failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 추론 등록 해제 보장 (성공/실패/예외 모두)
        await _unregister_inference(inference_id)


async def _run_vision_from_media_paths(
    media_paths: MediaPaths,
    zone_id: int,
) -> tuple:
    """
    이미지 경로에서 Vision 추론 수행.

    모든 카메라(cam0~cam5)를 자동 탐색하고 개별 결과를 반환합니다.
    연속 프레임이 있으면 Motion Correlation 분석을 수행하여 보너스를 부여합니다.

    Args:
        media_paths: 이미지/영상 경로
        zone_id: Zone ID

    Returns:
        (vision_candidates, images_processed, camera_results)
        - vision_candidates: Ensemble 결과
        - images_processed: 처리된 이미지 경로 목록
        - camera_results: 카메라별 결과 {cam0: {...}, cam1: {...}, ...}
    """
    from ..vision import (
        YOLOWrapper, Top5Extractor, MultiViewEnsemble,
        MotionCorrelationFilter, reset_motion_filter
    )

    vision_candidates = []
    images_processed = []
    camera_results = {}  # cam0, cam1, ... 개별 결과

    # 이미지 파일 경로 수집: (cam_id, cam_type, img_paths) 형식
    # img_paths는 연속 프레임 리스트 (motion tracking용)
    camera_image_map = {}  # {cam_id: {"cam_type": str, "images": [path1, path2, ...]}}

    # 명시적 top_image/side_image가 있으면 우선 사용
    if media_paths.top_image and os.path.exists(media_paths.top_image):
        camera_image_map[0] = {"cam_type": "top", "images": [media_paths.top_image]}

    if media_paths.side_image and os.path.exists(media_paths.side_image):
        side_cam_id = zone_id + 1
        camera_image_map[side_cam_id] = {"cam_type": "side", "images": [media_paths.side_image]}

    # image_folder가 있으면 모든 cam0~cam5 자동 탐색
    if media_paths.image_folder and not camera_image_map:
        folder = media_paths.image_folder
        if os.path.isdir(folder):
            # 모든 카메라 폴더 탐색 (cam0 ~ cam5)
            for cam_id in range(6):
                # 새 형식 (cam0) 우선, 이전 형식 (cam_0) 폴백
                cam_names = [f"cam{cam_id}", f"cam_{cam_id}"]
                for cam_name in cam_names:
                    cam_dir = os.path.join(folder, cam_name)
                    if os.path.isdir(cam_dir):
                        cam_type = "top" if cam_id == 0 else "side"

                        # 연속 프레임 탐색 (frame_0001.jpg, frame_0002.jpg, ...)
                        frame_files = sorted([
                            f for f in os.listdir(cam_dir)
                            if f.startswith("frame_") and f.endswith(".jpg")
                        ])

                        if frame_files:
                            # 연속 프레임 발견 → Motion Tracking 가능
                            frame_paths = [os.path.join(cam_dir, f) for f in frame_files]
                            camera_image_map[cam_id] = {"cam_type": cam_type, "images": frame_paths}
                        else:
                            # 단일 스냅샷 탐색
                            for img_file in ["snapshot.jpg", "frame.jpg", "capture.jpg"]:
                                img_path = os.path.join(cam_dir, img_file)
                                if os.path.exists(img_path):
                                    camera_image_map[cam_id] = {"cam_type": cam_type, "images": [img_path]}
                                    break
                        break  # 한 형식에서 찾았으면 다른 형식 탐색 불필요

    if not camera_image_map:
        logger.warning(
            f"No valid images found in media_paths: folder={media_paths.image_folder}, "
            f"top={media_paths.top_image}, side={media_paths.side_image}"
        )
        # 빈 결과 반환 (호출자가 no_images 상태 확인 가능)
        return vision_candidates, images_processed, camera_results

    # YOLO 추론 수행
    try:
        import cv2

        yolo = YOLOWrapper(model_path=config.yolo_model_path)
        top5_extractor = Top5Extractor()  # 내부적으로 HandProximityFilter 사용
        ensemble = MultiViewEnsemble(use_motion_tracking=config.use_motion_tracking)

        # Motion Tracking 필터 초기화
        motion_filter = MotionCorrelationFilter(
            max_motion_bonus=config.max_motion_bonus,
            min_correlation=config.min_motion_correlation,
            lookback_frames=config.motion_lookback_frames,
        )

        top_candidates = []
        all_side_candidates = []
        motion_bonus_map = {}

        # 연속 프레임이 있는지 확인
        has_multiple_frames = any(len(info["images"]) > 1 for info in camera_image_map.values())

        if has_multiple_frames:
            # ═══════════════════════════════════════════════════════════════
            # 연속 프레임 처리: Motion Tracking 수행
            # ═══════════════════════════════════════════════════════════════
            logger.info("Multiple frames detected, enabling motion tracking")

            # 모든 카메라의 최대 프레임 수
            max_frames = max(len(info["images"]) for info in camera_image_map.values())

            # 프레임별로 순차 처리
            for frame_idx in range(max_frames):
                all_frame_detections = []

                for cam_id, info in camera_image_map.items():
                    if frame_idx >= len(info["images"]):
                        continue

                    img_path = info["images"][frame_idx]
                    image = cv2.imread(img_path)
                    if image is None:
                        continue

                    # YOLO 추론
                    detections = yolo.detect(image)
                    all_frame_detections.extend(detections)

                    # 마지막 프레임이면 처리된 이미지 목록에 추가
                    if frame_idx == max_frames - 1:
                        images_processed.append(img_path)

                # Motion Filter 업데이트 (프레임별 호출로 히스토리 축적)
                if all_frame_detections:
                    motion_bonus_map = motion_filter.get_motion_bonus_map(all_frame_detections)

            logger.info(
                f"Motion tracking completed: {max_frames} frames, "
                f"{len(motion_bonus_map)} products with motion data"
            )

        # ═══════════════════════════════════════════════════════════════
        # 마지막 프레임 (또는 단일 스냅샷) 처리: 카메라별 결과 수집
        # ═══════════════════════════════════════════════════════════════
        for cam_id, info in camera_image_map.items():
            cam_key = f"cam{cam_id}"
            cam_type = info["cam_type"]
            img_path = info["images"][-1]  # 마지막 프레임

            try:
                # 이미지 로드
                image = cv2.imread(img_path)
                if image is None:
                    logger.warning(f"Failed to load image: {img_path}")
                    camera_results[cam_key] = {
                        "detected": False,
                        "confidence": 0.0,
                        "candidates": [],
                        "motion_bonus": 0.0,
                        "error": "failed_to_load",
                    }
                    continue

                # YOLO 추론
                detections = yolo.detect(image)
                if img_path not in images_processed:
                    images_processed.append(img_path)

                logger.info(f"YOLO detection result for {img_path}: {len(detections)} objects")
                for det in detections[:5]:  # 상위 5개만 로그
                    logger.debug(f"  - {det.name} (cls={det.cls}, conf={det.conf:.3f})")

                if not detections:
                    logger.debug(f"No detections in {img_path}")
                    camera_results[cam_key] = {
                        "detected": False,
                        "confidence": 0.0,
                        "candidates": [],
                        "motion_bonus": 0.0,
                    }
                    continue

                # 단일 스냅샷인데 motion tracking 안 했으면 여기서 업데이트
                if not has_multiple_frames and config.use_motion_tracking:
                    motion_bonus_map = motion_filter.get_motion_bonus_map(detections)

                # Top-5 추출 (내부에서 손 근접 필터링 수행)
                top5_result = top5_extractor.extract(detections)

                # 카메라별 결과 저장 (motion_bonus 포함)
                candidates_list = []
                for c in top5_result.candidates:
                    m_bonus = motion_bonus_map.get(c.cls, 0.0)
                    candidates_list.append({
                        "class_name": c.name,
                        "class_id": c.cls,
                        "confidence": round(c.conf, 3),
                        "motion_bonus": round(m_bonus, 3),
                    })

                max_conf = max((c.conf for c in top5_result.candidates), default=0.0)
                max_motion = max((motion_bonus_map.get(c.cls, 0.0) for c in top5_result.candidates), default=0.0)

                camera_results[cam_key] = {
                    "detected": len(top5_result.candidates) > 0,
                    "confidence": round(max_conf, 3),
                    "motion_bonus": round(max_motion, 3),
                    "candidates": candidates_list,
                }

                # Ensemble용 후보 수집
                if cam_type == "top":
                    top_candidates = top5_result.candidates
                else:
                    all_side_candidates.extend(top5_result.candidates)

                logger.info(
                    f"{cam_key} ({cam_type}): {len(detections)} detections, "
                    f"{len(top5_result.candidates)} candidates after filtering"
                )

            except Exception as e:
                logger.error(f"Vision processing failed for {img_path}: {e}", exc_info=True)
                camera_results[cam_key] = {
                    "detected": False,
                    "confidence": 0.0,
                    "candidates": [],
                    "motion_bonus": 0.0,
                    "error": str(e),
                }
                continue

        # ═══════════════════════════════════════════════════════════════
        # Multi-View Ensemble (Motion Bonus 포함)
        # ═══════════════════════════════════════════════════════════════
        if top_candidates or all_side_candidates:
            vision_candidates = ensemble.ensemble(
                top_candidates,
                all_side_candidates,
                motion_bonus_map=motion_bonus_map,
            )

            motion_applied = sum(1 for v in vision_candidates if motion_bonus_map.get(v.class_id, 0) > 0)
            logger.info(
                f"Ensemble result: {len(vision_candidates)} candidates "
                f"(top={len(top_candidates)}, sides={len(all_side_candidates)}, "
                f"motion_bonus_applied={motion_applied})"
            )

    except ImportError as e:
        logger.warning(f"Vision dependencies not available: {e}")
        images_processed = [info["images"][-1] for info in camera_image_map.values()]
    except Exception as e:
        logger.error(f"Vision pipeline error: {e}", exc_info=True)
        images_processed = [info["images"][-1] for info in camera_image_map.values()]

    return vision_candidates, images_processed, camera_results


# ===== Recording Data Processing =====

@router.post("/recording/process", response_model=RecordingProcessResponse)
async def process_recording_data(request: RecordingProcessRequest):
    """
    Recording 데이터 처리.

    IO Board에서 recording된 시리얼 데이터를 받아 WeightData로 변환합니다.
    return_raw=False이면 자동으로 판단도 수행합니다.

    요청 형식:
        {
            "recording": {
                "logs": [
                    {"loadcells": ["+01234", "-00567", ...], "timestamp": "..."},
                    ...
                ],
                "zone_id": 0,
                "zone_channels": [0, 1]  # 옵션, 없으면 자동 결정
            },
            "return_raw": false,
            "media_paths": {...}  # return_raw=false일 때
        }

    Args:
        request: Recording 처리 요청

    Returns:
        RecordingProcessResponse: 처리 결과
    """
    start_time = time.time()

    try:
        # Recording 데이터 처리
        recording_processor = RecordingProcessor()
        recording_logs = [
            {"loadcells": log.loadcells, "timestamp": log.timestamp}
            for log in request.recording.logs
        ]

        processed = recording_processor.process(
            recording_logs=recording_logs,
            zone_id=request.recording.zone_id,
            zone_channels=request.recording.zone_channels,
        )

        weight_data = convert_to_weight_data(processed)

        processing_info = {
            "sample_count": processed.sample_count,
            "baseline_sample_count": processed.baseline_sample_count,
            "current_sample_count": processed.current_sample_count,
            "zone_id": processed.zone_id,
            "changed_channels": processed.channels,
        }

        logger.info(
            f"Recording processed: zone={processed.zone_id}, "
            f"delta={processed.delta_weight:.1f}g, samples={processed.sample_count}"
        )

        return RecordingProcessResponse(
            success=True,
            weight_data=weight_data,
            processing_info=processing_info,
            timestamp=time.time(),
        )

    except Exception as e:
        logger.error(f"Recording processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recording/judge")
async def judge_from_recording(request: RecordingProcessRequest):
    """
    Recording 데이터로 상품 판단 수행.

    IO Board에서 recording된 시리얼 데이터를 받아 WeightData로 변환하고,
    media_paths가 있으면 Vision 추론도 함께 수행합니다.

    요청 형식:
        {
            "recording": {
                "logs": [
                    {"loadcells": ["+01234", "-00567", ...], "timestamp": "..."},
                    ...
                ],
                "zone_id": 0
            },
            "media_paths": {
                "image_folder": "/data/snapshots/260126143025"
            }
        }

    Args:
        request: Recording 처리 요청

    Returns:
        JudgeResponse: 판단 결과
    """
    global _decision_engine

    if _decision_engine is None:
        raise HTTPException(status_code=503, detail="Decision engine not initialized")

    start_time = time.time()
    images_processed = []
    camera_results = {}

    try:
        # Recording 데이터 처리
        recording_processor = RecordingProcessor()
        recording_logs = [
            {"loadcells": log.loadcells, "timestamp": log.timestamp}
            for log in request.recording.logs
        ]

        processed = recording_processor.process(
            recording_logs=recording_logs,
            zone_id=request.recording.zone_id,
            zone_channels=request.recording.zone_channels,
        )

        delta_weight = processed.delta_weight
        zone_id = request.recording.zone_id

        logger.info(
            f"Recording judge: zone={zone_id}, delta={delta_weight:.1f}g, "
            f"samples={processed.sample_count}"
        )

        # Vision 추론 (media_paths가 있는 경우)
        vision_candidates = []
        if request.media_paths is not None:
            vision_candidates, images_processed, camera_results = await _run_vision_from_media_paths(
                request.media_paths,
                zone_id,
            )
            logger.info(f"Vision inference: {len(vision_candidates)} candidates from {len(images_processed)} images")

        # 판단 수행
        result = _decision_engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=delta_weight,
        )

        # 처리 시간 계산
        processing_time_ms = (time.time() - start_time) * 1000

        # 응답 생성
        response = {
            "success": result.is_success,
            "products": [
                {
                    "productId": p.product_id,
                    "name": p.name,
                    "count": p.count,
                    "unitPrice": p.unit_price,
                    "totalPrice": p.total_price,
                    "confidence": round(p.confidence, 2),
                }
                for p in result.products
            ],
            "totalPrice": result.total_price,
            "status": result.status.value,
            "confidence": round(result.confidence, 2),
            "weightInfo": {
                "delta": round(result.weight_delta, 1),
                "explained": round(result.weight_explained, 1),
                "residual": round(result.weight_residual, 1),
            },
            "productCount": result.product_count,
            "isRemoval": result.is_removal,
            "timestamp": time.time(),
            "recording_info": {
                "sample_count": processed.sample_count,
                "baseline_samples": processed.baseline_sample_count,
                "current_samples": processed.current_sample_count,
                "changed_channels": processed.channels,
            },
            "camera_results": camera_results if camera_results else None,
            "processing_time_ms": round(processing_time_ms, 1),
        }

        logger.info(
            f"Recording judge result: status={result.status.value}, "
            f"products={len(result.products)}, totalPrice={result.total_price}, "
            f"processing_time={processing_time_ms:.1f}ms"
        )

        return response

    except Exception as e:
        logger.error(f"Recording judge failed: {e}", exc_info=True)
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


# ===== Product Registration Endpoints =====

# 이미지 저장 기본 경로 (config에서 가져오거나 기본값 사용)
_IMAGE_BASE_PATH = os.environ.get(
    "PRODUCT_IMAGE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "images")
)


@router.post("/products/register", response_model=ProductRegisterResponse)
async def register_product(request: ProductRegisterRequest):
    """
    새 상품 등록.

    점주가 새 상품을 등록합니다.

    Args:
        request: 상품 등록 요청

    Returns:
        ProductRegisterResponse: 등록된 상품 정보
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    try:
        product_id = _product_db.add_product(
            name=request.name,
            category=request.category,
            weight=request.weight,
            price=request.price,
            barcode=request.barcode,
            stock=request.stock,
        )

        logger.info(f"Product registered: id={product_id}, name={request.name}")

        return ProductRegisterResponse(
            success=True,
            product_id=product_id,
            name=request.name,
            status="registered",
            timestamp=time.time(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Product registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/products/{product_id}", response_model=ProductUpdateResponse)
async def update_product(product_id: int, request: ProductUpdateRequest):
    """
    상품 정보 수정.

    Args:
        product_id: 상품 ID
        request: 수정할 필드

    Returns:
        ProductUpdateResponse: 수정 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    try:
        success = _product_db.update_product(
            product_id=product_id,
            name=request.name,
            category=request.category,
            weight=request.weight,
            price=request.price,
            barcode=request.barcode,
            stock=request.stock,
        )

        if not success:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

        logger.info(f"Product updated: id={product_id}")

        return ProductUpdateResponse(
            success=True,
            product_id=product_id,
            message="Product updated successfully",
            timestamp=time.time(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Product update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/products/{product_id}", response_model=ProductDeleteResponse)
async def delete_product(product_id: int):
    """
    상품 삭제.

    Args:
        product_id: 상품 ID

    Returns:
        ProductDeleteResponse: 삭제 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    # hand(0) 삭제 방지
    if product_id == 0:
        raise HTTPException(status_code=400, detail="Cannot delete hand class (id=0)")

    success = _product_db.delete_product(product_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    logger.info(f"Product deleted: id={product_id}")

    return ProductDeleteResponse(
        success=True,
        product_id=product_id,
        message="Product deleted successfully",
        timestamp=time.time(),
    )


@router.post("/products/{product_id}/images", response_model=ImageUploadResponse)
async def upload_product_images(
    product_id: int,
    camera_id: int = Form(..., ge=0, le=5, description="카메라 ID (0=Top, 1-5=Zone)"),
    images: List[UploadFile] = File(..., description="이미지 파일들"),
):
    """
    상품 이미지 업로드.

    카메라별로 이미지를 저장합니다.

    저장 구조:
    ```
    {base_path}/images/
    └── cam_{camera_id}/
        ├── product_{product_id}_001.jpg
        ├── product_{product_id}_002.jpg
        └── ...
    ```

    Args:
        product_id: 상품 ID
        camera_id: 카메라 ID (0=Top, 1-5=Zone)
        images: 이미지 파일 리스트

    Returns:
        ImageUploadResponse: 업로드 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    # 상품 존재 확인
    product = _product_db.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    # 이미지 저장 디렉토리 생성
    cam_dir = os.path.join(_IMAGE_BASE_PATH, f"cam_{camera_id}")
    os.makedirs(cam_dir, exist_ok=True)

    # 기존 이미지 수 확인 (파일명 번호 결정용)
    existing_images = list(Path(cam_dir).glob(f"product_{product_id:03d}_*.jpg"))
    next_num = len(existing_images) + 1

    saved_count = 0
    for image in images:
        # 파일 확장자 확인
        if not image.filename.lower().endswith((".jpg", ".jpeg", ".png")):
            logger.warning(f"Skipping non-image file: {image.filename}")
            continue

        # 파일명 생성
        filename = f"product_{product_id:03d}_{next_num:03d}.jpg"
        filepath = os.path.join(cam_dir, filename)

        try:
            # 파일 저장
            with open(filepath, "wb") as f:
                content = await image.read()
                f.write(content)

            saved_count += 1
            next_num += 1
            logger.debug(f"Image saved: {filepath}")

        except Exception as e:
            logger.error(f"Failed to save image {image.filename}: {e}")

    # 상품 이미지 수 갱신
    if saved_count > 0:
        _product_db.increment_image_count(product_id, saved_count)

    total_images = product.image_count + saved_count

    logger.info(
        f"Product images uploaded: product_id={product_id}, "
        f"camera_id={camera_id}, saved={saved_count}"
    )

    return ImageUploadResponse(
        success=True,
        product_id=product_id,
        camera_id=camera_id,
        saved_count=saved_count,
        save_path=f"images/cam_{camera_id}/",
        total_images=total_images,
        timestamp=time.time(),
    )


@router.get("/products/export", response_model=ProductExportResponse)
async def export_products():
    """
    전체 상품 목록 내보내기.

    Node.js 동기화 및 외부 시스템 연동용.

    Returns:
        ProductExportResponse: 전체 상품 목록
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    products = _product_db.export_all(exclude_hand=True)

    return ProductExportResponse(
        success=True,
        products=products,
        count=len(products),
        timestamp=time.time(),
    )


@router.get("/products/search")
async def search_products(query: str, limit: int = 10):
    """
    상품 이름 검색.

    Args:
        query: 검색어 (부분 일치)
        limit: 최대 결과 수 (기본 10)

    Returns:
        검색 결과 리스트
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    matches = _product_db.search_by_name(query, limit=min(limit, 100))

    return {
        "success": True,
        "query": query,
        "products": [
            {
                "product_id": p.product_id,
                "name": p.name,
                "category": p.category,
                "weight": p.weight,
                "price": p.price,
            }
            for p in matches
        ],
        "count": len(matches),
        "timestamp": time.time(),
    }


@router.get("/products/barcode/{barcode}")
async def get_product_by_barcode(barcode: str):
    """
    바코드로 상품 조회.

    Args:
        barcode: 바코드

    Returns:
        상품 정보
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    product = _product_db.get_by_barcode(barcode)

    if product is None:
        raise HTTPException(status_code=404, detail=f"Product with barcode {barcode} not found")

    return {
        "success": True,
        "product": {
            "product_id": product.product_id,
            "name": product.name,
            "category": product.category,
            "weight": product.weight,
            "price": product.price,
            "barcode": product.barcode,
            "stock": product.stock,
        },
        "timestamp": time.time(),
    }


class IF11ProductItem(BaseModel):
    """IF11 형식의 상품 항목."""
    product_idx: str = Field(..., description="상품 ID (예: P17355176364813008)")
    product_name: str = Field(..., description="상품명")
    sale_price: int = Field(0, description="판매가")
    stock_qty: int = Field(0, description="재고 수량")
    product_weight: str = Field("0", description="상품 무게 (문자열)")
    # YOLO 매핑 확장 필드 (Node.js ProductSyncService에서 전달)
    yolo_class_id: Optional[int] = Field(None, description="YOLO 클래스 ID")
    yolo_class_name: Optional[str] = Field(None, description="YOLO 클래스 이름")
    category: Optional[str] = Field(None, description="상품 카테고리")


class IF11ProductListRequest(BaseModel):
    """IF11 상품 리스트 요청."""
    product_list: List[IF11ProductItem] = Field(..., description="상품 리스트")


@router.post("/products/sync")
async def sync_products_from_if11(request: IF11ProductListRequest):
    """
    IF11 형식의 상품 리스트 동기화.

    Node.js에서 IF11 형식으로 상품 리스트를 전달받아 데이터베이스를 갱신합니다.
    yolo_class_id와 yolo_class_name이 포함된 경우 YOLO 매핑도 함께 등록합니다.

    README.md Step 5.1: 상품 정보(상품명, 무게, 재고) + 스냅샷 경로 (node → model)

    IF11 형식 예시:
        {
            "product_idx": "P17355176364813008",
            "product_name": "페리에 330ml",
            "sale_price": 1985,
            "stock_qty": 12,
            "product_weight": "550"
        }

    확장 형식 (YOLO 매핑 포함):
        {
            "product_idx": "DEMO_109",
            "product_name": "달광도넛 초코",
            "sale_price": 1500,
            "stock_qty": 10,
            "product_weight": "45",
            "yolo_class_id": 109,
            "yolo_class_name": "BAG_DALGWANG_DONUT_CHOCO_45G",
            "category": "snack"
        }

    Args:
        request: IF11 형식의 상품 리스트

    Returns:
        동기화 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    try:
        loaded_count = 0
        yolo_mapped_count = 0

        for item in request.product_list:
            # YOLO 매핑 정보가 있는지 확인
            has_yolo_mapping = item.yolo_class_id is not None and item.yolo_class_name is not None

            if has_yolo_mapping:
                # YOLO 클래스 기반으로 상품 등록/업데이트
                yolo_class_id = item.yolo_class_id
                yolo_class_name = item.yolo_class_name

                # 기존 상품 확인
                existing = _product_db.get_by_yolo_class_id(yolo_class_id)

                if existing:
                    # 기존 상품 업데이트
                    _product_db.update_product(
                        product_id=existing.product_id,
                        name=item.product_name,
                        category=item.category or _product_db._guess_category(item.product_name),
                        weight=float(item.product_weight) if item.product_weight else 0.0,
                        price=item.sale_price,
                        stock=item.stock_qty,
                    )
                    loaded_count += 1
                else:
                    # 새 상품 생성 (YOLO class_id를 product_id로 사용)
                    try:
                        product_id = _product_db.add_product(
                            name=item.product_name,
                            category=item.category or _product_db._guess_category(item.product_name),
                            weight=float(item.product_weight) if item.product_weight else 0.0,
                            price=item.sale_price,
                            stock=item.stock_qty,
                            product_id=yolo_class_id,  # YOLO class_id를 product_id로 사용
                        )

                        # YOLO 매핑 등록
                        product = _product_db.get_product(product_id)
                        if product:
                            product.yolo_class_id = yolo_class_id
                            product.yolo_class_name = yolo_class_name
                            product.product_idx = item.product_idx
                            _product_db._yolo_to_product[yolo_class_id] = product_id
                            _product_db._yolo_name_to_id[yolo_class_name] = product_id
                            _product_db._product_idx_to_id[item.product_idx] = product_id
                            yolo_mapped_count += 1

                        loaded_count += 1
                    except ValueError as e:
                        # ID 충돌 시 기존 상품 업데이트
                        if yolo_class_id in _product_db._products:
                            _product_db.update_product(
                                product_id=yolo_class_id,
                                name=item.product_name,
                                category=item.category or _product_db._guess_category(item.product_name),
                                weight=float(item.product_weight) if item.product_weight else 0.0,
                                price=item.sale_price,
                                stock=item.stock_qty,
                            )
                            product = _product_db.get_product(yolo_class_id)
                            if product:
                                product.yolo_class_id = yolo_class_id
                                product.yolo_class_name = yolo_class_name
                                product.product_idx = item.product_idx
                                _product_db._yolo_to_product[yolo_class_id] = yolo_class_id
                                _product_db._yolo_name_to_id[yolo_class_name] = yolo_class_id
                                _product_db._product_idx_to_id[item.product_idx] = yolo_class_id
                            loaded_count += 1
                            yolo_mapped_count += 1
                        else:
                            logger.warning(f"Failed to add product {item.product_name}: {e}")
            else:
                # 기존 IF11 형식 처리 (YOLO 매핑 없음)
                product_dict = {
                    "product_idx": item.product_idx,
                    "product_name": item.product_name,
                    "sale_price": item.sale_price,
                    "stock_qty": item.stock_qty,
                    "product_weight": item.product_weight,
                }
                # 개별 로드
                count = _product_db.load_from_if11([product_dict])
                loaded_count += count

        logger.info(
            f"Products synced: {loaded_count} total, {yolo_mapped_count} with YOLO mapping"
        )

        return {
            "success": True,
            "loaded_count": loaded_count,
            "yolo_mapped_count": yolo_mapped_count,
            "total_products": _product_db.product_count,
            "message": f"Successfully synced {loaded_count} products ({yolo_mapped_count} with YOLO mapping)",
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to sync products from IF11: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/products/save")
async def save_products_to_file(path: Optional[str] = None):
    """
    상품 데이터베이스 저장.

    Args:
        path: 저장 경로 (선택)

    Returns:
        저장 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    try:
        _product_db.save_to_file(path)
        return {
            "success": True,
            "message": "Product database saved",
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Failed to save products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== YOLO-IF11 Mapping Endpoints =====

@router.get("/products/yolo-mapping")
async def get_all_yolo_mappings():
    """
    전체 YOLO-IF11 매핑 조회.

    YOLO 모델 클래스와 IF11 상품 간의 모든 매핑 정보를 반환합니다.

    Returns:
        매핑 정보 리스트
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    mappings = _product_db.get_all_yolo_mappings()

    # 통계 계산
    linked_count = sum(1 for m in mappings if m.get("is_linked"))
    unlinked_count = len(mappings) - linked_count

    return {
        "success": True,
        "mappings": mappings,
        "count": len(mappings),
        "linked_count": linked_count,
        "unlinked_count": unlinked_count,
        "timestamp": time.time(),
    }


@router.get("/products/yolo-mapping/{class_id}")
async def get_yolo_mapping(class_id: int):
    """
    특정 YOLO 클래스의 매핑 정보 조회.

    Args:
        class_id: YOLO 클래스 ID

    Returns:
        매핑 정보
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    mapping = _product_db.get_yolo_mapping(class_id)

    if mapping is None:
        raise HTTPException(status_code=404, detail=f"YOLO class {class_id} not found")

    return {
        "success": True,
        "mapping": mapping,
        "timestamp": time.time(),
    }


class YoloAutoMatchRequest(BaseModel):
    """YOLO 자동 매칭 요청."""
    force_rematch: bool = Field(
        False,
        description="기존 매핑을 무시하고 다시 매칭할지 여부",
    )


@router.post("/products/yolo-mapping/auto")
async def auto_match_yolo_to_if11(request: Optional[YoloAutoMatchRequest] = None):
    """
    YOLO 클래스와 IF11 상품 자동 매칭.

    YOLO 클래스명과 IF11 상품명을 비교하여 자동으로 매칭합니다.
    키워드 유사도와 무게 일치를 기준으로 매칭합니다.

    Args:
        request: 자동 매칭 요청 옵션

    Returns:
        매칭 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    try:
        matched_count = _product_db.auto_match_yolo_to_if11()

        return {
            "success": True,
            "matched_count": matched_count,
            "message": f"Auto-matched {matched_count} YOLO classes to IF11 products",
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Auto-match failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class YoloLinkRequest(BaseModel):
    """YOLO-IF11 수동 연결 요청."""
    yolo_class_id: int = Field(..., description="YOLO 클래스 ID")
    product_idx: str = Field(..., description="IF11 상품 ID (예: P17689508539755305)")


@router.post("/products/yolo-mapping/link")
async def link_yolo_to_if11(request: YoloLinkRequest):
    """
    YOLO 클래스와 IF11 상품 수동 연결.

    자동 매칭이 실패한 경우 수동으로 연결할 수 있습니다.

    Args:
        request: 연결 요청 (yolo_class_id, product_idx)

    Returns:
        연결 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    try:
        success = _product_db.link_yolo_to_if11(
            yolo_class_id=request.yolo_class_id,
            product_idx=request.product_idx,
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to link YOLO class {request.yolo_class_id} to IF11 product {request.product_idx}",
            )

        # 연결된 상품 정보 반환
        mapping = _product_db.get_yolo_mapping(request.yolo_class_id)

        return {
            "success": True,
            "mapping": mapping,
            "message": f"Linked YOLO class {request.yolo_class_id} to IF11 product {request.product_idx}",
            "timestamp": time.time(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Link failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class YoloMappingSaveRequest(BaseModel):
    """YOLO 매핑 파일 저장 요청."""
    path: Optional[str] = Field(
        None,
        description="저장 경로 (None이면 기본 경로 사용)",
    )


@router.post("/products/yolo-mapping/save")
async def save_yolo_mapping(request: Optional[YoloMappingSaveRequest] = None):
    """
    YOLO-IF11 매핑 파일 저장.

    현재 매핑 상태를 JSON 파일로 저장합니다.

    Args:
        request: 저장 요청 (선택적 경로)

    Returns:
        저장 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    try:
        path = request.path if request else None
        if not path:
            # 기본 경로 사용
            path = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "config", "yolo_product_mapping.json"
            )

        success = _product_db.save_mapping_file(path)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save mapping file")

        return {
            "success": True,
            "path": path,
            "message": "Mapping file saved successfully",
            "timestamp": time.time(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save mapping failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class YoloMappingLoadRequest(BaseModel):
    """YOLO 매핑 파일 로드 요청."""
    path: Optional[str] = Field(
        None,
        description="로드 경로 (None이면 기본 경로 사용)",
    )


@router.post("/products/yolo-mapping/load")
async def load_yolo_mapping(request: Optional[YoloMappingLoadRequest] = None):
    """
    YOLO-IF11 매핑 파일 로드.

    저장된 매핑 파일을 로드합니다.

    Args:
        request: 로드 요청 (선택적 경로)

    Returns:
        로드 결과
    """
    global _product_db

    if _product_db is None:
        raise HTTPException(status_code=503, detail="Product database not initialized")

    try:
        path = request.path if request else None
        if not path:
            # 기본 경로 사용
            path = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "config", "yolo_product_mapping.json"
            )

        loaded_count = _product_db.load_mapping_file(path)

        return {
            "success": True,
            "path": path,
            "loaded_count": loaded_count,
            "message": f"Loaded {loaded_count} mappings from file",
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Load mapping failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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


# ===== Advanced Endpoints =====

@router.post("/judge/multi-zone", response_model=MultiZoneJudgeResponse)
async def judge_multi_zone(request: MultiZoneJudgeRequest):
    """
    다중 Zone 동시 판단.

    여러 Zone에서 동시에 발생한 무게 변화를 판단하고,
    Cross-Zone 이동을 감지합니다.

    Args:
        request: 다중 Zone 판단 요청

    Returns:
        MultiZoneJudgeResponse: 다중 Zone 판단 결과
    """
    global _decision_engine, _cross_zone_detector, _baseline_manager
    global _multi_zone_monitor, _stats, _zone_stats

    if _decision_engine is None:
        raise HTTPException(status_code=503, detail="Decision engine not initialized")

    current_time = time.time()
    logger.info(f"Multi-zone judge request: {len(request.zone_deltas)} zones")

    try:
        zone_results: List[ZoneJudgmentResult] = []
        total_price = 0

        # 각 Zone 처리
        for zone_delta in request.zone_deltas:
            zone_id = zone_delta.zone_id
            delta = zone_delta.delta

            # Drift 보정 (도어 오픈 시간이 있는 경우)
            if request.door_open_duration and _baseline_manager:
                delta = _baseline_manager.get_long_open_correction(
                    zone_id=zone_id,
                    door_open_duration=request.door_open_duration,
                    current_weight=delta,  # 이 경우 delta가 현재 무게로 사용됨
                )

            # Multi-zone monitor 업데이트
            if _multi_zone_monitor:
                _multi_zone_monitor.update(zone_id, delta)

            # Zone별 Vision 후보군 필터링
            zone_candidates = []
            if request.vision_candidates:
                zone_candidates = [
                    EnsembleResult(
                        class_id=c.class_id,
                        class_name=c.class_name,
                        top_confidence=c.confidence,
                        side_confidence=c.confidence,
                        combined_confidence=c.confidence,
                        vote_count=1,
                    )
                    for c in request.vision_candidates
                    if c.zone_id is None or c.zone_id == zone_id
                ]

            # 판단 수행
            result = _decision_engine.judge(
                vision_candidates=zone_candidates,
                delta_weight=delta,
            )

            # 통계 업데이트 (활성화된 zone만)
            _stats["total_events"] += 1
            if zone_id in _zone_stats:
                _zone_stats[zone_id]["total_events"] += 1

            if result.is_success:
                _stats["successful_judgments"] += 1
                if zone_id in _zone_stats:
                    _zone_stats[zone_id]["successful_judgments"] += 1
            else:
                _stats["failed_judgments"] += 1
                if zone_id in _zone_stats:
                    _zone_stats[zone_id]["failed_judgments"] += 1

            # 결과 생성
            zone_result = ZoneJudgmentResult(
                zone_id=zone_id,
                products=[
                    {
                        "productId": p.product_id,
                        "name": p.name,
                        "count": p.count,
                        "unitPrice": p.unit_price,
                        "totalPrice": p.total_price,
                        "confidence": round(p.confidence, 2),
                    }
                    for p in result.products
                ],
                total_price=result.total_price,
                status=JudgmentStatusEnum(result.status.value),
                confidence=round(result.confidence, 2),
                weight_delta=round(delta, 1),
                weight_explained=round(result.weight_explained, 1),
            )

            zone_results.append(zone_result)
            total_price += result.total_price

        # Cross-Zone 이동 감지
        cross_zone_result = None
        if request.check_cross_zone and _multi_zone_monitor:
            movement = _multi_zone_monitor.detect_cross_zone_movement()
            if movement.detected:
                _stats["cross_zone_moves"] += 1
                cross_zone_result = CrossZoneMovementResult(
                    detected=True,
                    source_zone=movement.source_zone,
                    target_zone=movement.target_zone,
                    weight=round(movement.weight, 1),
                    match_score=round(movement.match_score, 3),
                )
                logger.info(
                    f"Cross-zone movement detected: "
                    f"Zone {movement.source_zone} -> Zone {movement.target_zone}"
                )

        response = MultiZoneJudgeResponse(
            success=True,
            zone_results=zone_results,
            cross_zone_movement=cross_zone_result,
            total_price=total_price,
            timestamp=current_time,
        )

        logger.info(
            f"Multi-zone judge completed: {len(zone_results)} zones, "
            f"total_price={total_price}"
        )

        return response

    except Exception as e:
        logger.error(f"Multi-zone judge failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/judge/with-history", response_model=HistoryJudgeResponse)
async def judge_with_history(request: HistoryJudgeRequest):
    """
    히스토리 기반 판단.

    최근 이벤트 히스토리를 고려하여 반환 감지 및 연속 픽업을 처리합니다.

    Args:
        request: 히스토리 기반 판단 요청

    Returns:
        HistoryJudgeResponse: 히스토리 기반 판단 결과
    """
    global _decision_engine, _return_detector, _rapid_pickup_handler
    global _event_tracker, _stats

    if _decision_engine is None:
        raise HTTPException(status_code=503, detail="Decision engine not initialized")

    current_time = request.current_request.timestamp or time.time()
    logger.info(f"History-based judge request: zone={request.current_request.zone_id}")

    try:
        current_req = request.current_request
        delta_weight = current_req.delta_weight
        zone_id = current_req.zone_id

        # 반환 감지
        return_detection = None
        is_return_event = False

        if request.check_return and _return_detector and delta_weight > 0:
            # 이전 픽업 이벤트와 매칭
            for event in request.recent_events:
                if event.direction.value == "pickup" and event.zone_id == zone_id:
                    # 무게 매칭 확인
                    weight_diff = abs(abs(event.delta_weight) - delta_weight)
                    tolerance = abs(event.delta_weight) * 0.15  # 15% 허용

                    if weight_diff <= tolerance:
                        match_score = 1.0 - (weight_diff / abs(event.delta_weight))
                        return_detection = ReturnDetectionResult(
                            detected=True,
                            original_pickup_timestamp=event.timestamp,
                            returned_product_id=event.product_id,
                            returned_product_name=event.product_name,
                            weight_match_score=round(match_score, 3),
                        )
                        is_return_event = True
                        _stats["return_events"] += 1
                        logger.info(
                            f"Return detected: product={event.product_name}, "
                            f"match_score={match_score:.3f}"
                        )
                        break

        # 연속 픽업 감지
        rapid_pickup = None

        if request.check_rapid_pickup and _rapid_pickup_handler:
            _rapid_pickup_handler.add_event(
                delta_weight=delta_weight,
                timestamp=current_time,
                zone_id=zone_id,
            )

            if _rapid_pickup_handler.is_settled(current_time):
                buffer_result = _rapid_pickup_handler.peek_buffer()
                if buffer_result.event_count > 1:
                    rapid_pickup = RapidPickupResultModel(
                        detected=True,
                        event_count=buffer_result.event_count,
                        total_delta=round(buffer_result.total_delta, 1),
                        duration=round(buffer_result.duration, 2),
                        is_settled=True,
                    )
                    logger.info(
                        f"Rapid pickup detected: {buffer_result.event_count} events, "
                        f"total_delta={buffer_result.total_delta:.1f}g"
                    )
                    # 버퍼 사용 (flush)
                    delta_weight = _rapid_pickup_handler.flush_buffer().total_delta

        # 판단 수행 (반환 이벤트가 아닌 경우)
        if is_return_event:
            # 반환 이벤트는 가격 0, 상품 없음
            products = []
            total_price = 0
            status = JudgmentStatusEnum.COMPLETE
            confidence = return_detection.weight_match_score if return_detection else 0.0
        else:
            # Vision 후보군 처리
            vision_candidates = []
            if current_req.vision_candidates:
                vision_candidates = [
                    EnsembleResult(
                        class_id=c.class_id,
                        class_name=c.class_name,
                        top_confidence=c.confidence,
                        side_confidence=c.confidence,
                        combined_confidence=c.confidence,
                        vote_count=1,
                    )
                    for c in current_req.vision_candidates
                ]

            result = _decision_engine.judge(
                vision_candidates=vision_candidates,
                delta_weight=delta_weight,
            )

            products = [
                {
                    "productId": p.product_id,
                    "name": p.name,
                    "count": p.count,
                    "unitPrice": p.unit_price,
                    "totalPrice": p.total_price,
                    "confidence": round(p.confidence, 2),
                }
                for p in result.products
            ]
            total_price = result.total_price
            status = JudgmentStatusEnum(result.status.value)
            confidence = round(result.confidence, 2)

        response = HistoryJudgeResponse(
            success=True,
            products=products,
            total_price=total_price,
            status=status,
            confidence=confidence,
            return_detection=return_detection,
            rapid_pickup=rapid_pickup,
            is_return_event=is_return_event,
            timestamp=current_time,
        )

        logger.info(
            f"History-based judge completed: "
            f"is_return={is_return_event}, products={len(products)}"
        )

        return response

    except Exception as e:
        logger.error(f"History-based judge failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/recognition-rate", response_model=RecognitionRateResponse)
async def get_recognition_rate():
    """
    인식률 통계 조회.

    전체 및 Zone별 인식률 통계를 반환합니다.

    Returns:
        RecognitionRateResponse: 인식률 통계
    """
    global _stats, _zone_stats

    current_time = time.time()

    # 전체 인식률 계산
    total = _stats["total_events"]
    successful = _stats["successful_judgments"]
    overall_rate = successful / total if total > 0 else 0.0

    # Zone별 통계 생성 (활성화된 zone만)
    zone_statistics = []
    for zone_id in get_enabled_zones():
        zone_data = _zone_stats.get(zone_id, {
            "total_events": 0,
            "successful_judgments": 0,
            "failed_judgments": 0,
            "return_events": 0,
            "cross_zone_moves": 0,
        })
        zone_total = zone_data["total_events"]
        zone_successful = zone_data["successful_judgments"]
        zone_rate = zone_successful / zone_total if zone_total > 0 else 0.0

        zone_statistics.append(
            ZoneStatistics(
                zone_id=zone_id,
                total_events=zone_total,
                successful_judgments=zone_successful,
                failed_judgments=zone_data["failed_judgments"],
                return_events=zone_data["return_events"],
                cross_zone_moves=zone_data["cross_zone_moves"],
                recognition_rate=round(zone_rate, 3),
            )
        )

    response = RecognitionRateResponse(
        overall_recognition_rate=round(overall_rate, 3),
        total_events=total,
        successful_judgments=successful,
        zone_statistics=zone_statistics,
        recent_period_hours=24.0,  # 현재는 세션 기반, 추후 시간 기반으로 확장 가능
        timestamp=current_time,
    )

    logger.info(f"Recognition rate: {overall_rate:.1%} ({successful}/{total})")

    return response


@router.post("/stats/reset")
async def reset_statistics():
    """
    통계 초기화.

    모든 인식률 통계를 초기화합니다.

    Returns:
        dict: 초기화 결과
    """
    global _stats, _zone_stats

    _stats = {
        "total_events": 0,
        "successful_judgments": 0,
        "failed_judgments": 0,
        "return_events": 0,
        "cross_zone_moves": 0,
    }

    # 활성화된 zone만 초기화
    _init_zone_stats()

    enabled_zones = get_enabled_zones()
    logger.info(f"Statistics reset for zones: {enabled_zones}")

    return {
        "success": True,
        "message": f"Statistics reset successfully for {len(enabled_zones)} zones",
        "enabled_zones": enabled_zones,
        "timestamp": time.time(),
    }


# =============================================================================
# Door Payment Endpoints (도어 제어 + 결제 흐름)
# =============================================================================
# Note: 실제 결제 처리(card_terminal 연동)는 추후 구현 예정
#       현재는 기본 흐름과 상태 관리만 제공합니다.
# =============================================================================

from ..door_payment import (
    DoorPaymentController,
    CardInfo,
    ProductItem as DoorProductItem,
    TransactionState,
    TransactionResult,
)

# 도어 결제 컨트롤러 인스턴스
_door_payment_controller: Optional[DoorPaymentController] = None


def initialize_door_payment_controller(
    card_terminal_url: str = "http://127.0.0.1:8004",
):
    """도어 결제 컨트롤러 초기화."""
    global _door_payment_controller
    _door_payment_controller = DoorPaymentController(
        card_terminal_url=card_terminal_url,
    )
    logger.info("Door payment controller initialized")


# Request/Response Models for Door Payment
class DoorPaymentProductItem(BaseModel):
    """상품 항목 (도어 결제용)."""
    product_id: str = Field(..., description="상품 ID")
    name: str = Field(..., description="상품명")
    price: int = Field(..., description="단가 (원)")
    quantity: int = Field(1, description="수량")


class DoorPaymentRequest(BaseModel):
    """도어 결제 요청."""
    card_number: str = Field(..., description="카드 번호 (마스킹)")
    card_type: str = Field("CREDIT", description="카드 종류")
    issuer: str = Field("", description="발급사")
    products: List[DoorPaymentProductItem] = Field(..., description="구매 상품 목록")
    total_amount: int = Field(..., description="총 결제 금액")


class DoorPaymentResponse(BaseModel):
    """도어 결제 응답."""
    success: bool = Field(..., description="성공 여부")
    transaction_id: str = Field(..., description="거래 ID")
    state: str = Field(..., description="거래 상태")
    products: List[dict] = Field(..., description="상품 목록")
    total_amount: int = Field(..., description="총 금액")
    paid_amount: int = Field(..., description="결제 금액")
    error_message: str = Field("", description="에러 메시지")
    duration_seconds: Optional[float] = Field(None, description="소요 시간 (초)")


class DoorStatusResponse(BaseModel):
    """도어 상태 응답."""
    current_state: str = Field(..., description="현재 거래 상태")
    door_state: str = Field(..., description="도어 상태")
    deadbolt_state: str = Field(..., description="데드볼트 상태")


@router.post("/door/transaction", response_model=DoorPaymentResponse)
async def start_door_transaction(request: DoorPaymentRequest):
    """
    도어 결제 거래 시작.

    카드 정보와 상품 목록을 받아 결제 흐름을 시작합니다.

    흐름:
    1. 카드 정보 수신 → 데드볼트 해제
    2. 문 열림/닫힘 대기
    3. 일정 시간 후 데드볼트 잠금
    4. 결제 처리

    Args:
        request: 도어 결제 요청

    Returns:
        DoorPaymentResponse: 거래 결과
    """
    global _door_payment_controller

    if _door_payment_controller is None:
        # 컨트롤러 미초기화 시 자동 초기화
        initialize_door_payment_controller()

    logger.info(f"Door transaction request: {request.total_amount}원, {len(request.products)}개 상품")

    try:
        card_info = CardInfo(
            card_number=request.card_number,
            card_type=request.card_type,
            issuer=request.issuer,
        )

        products = [
            DoorProductItem(
                product_id=p.product_id,
                name=p.name,
                price=p.price,
                quantity=p.quantity,
            )
            for p in request.products
        ]

        result = await _door_payment_controller.process_transaction(
            card_info=card_info,
            products=products,
            total_amount=request.total_amount,
        )

        return DoorPaymentResponse(
            success=result.success,
            transaction_id=result.transaction_id,
            state=result.state.value,
            products=[
                {
                    "product_id": p.product_id,
                    "name": p.name,
                    "price": p.price,
                    "quantity": p.quantity,
                    "subtotal": p.subtotal,
                }
                for p in result.products
            ],
            total_amount=result.total_amount,
            paid_amount=result.paid_amount,
            error_message=result.error_message,
            duration_seconds=result.duration_seconds,
        )

    except Exception as e:
        logger.error(f"Door transaction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/door/status", response_model=DoorStatusResponse)
async def get_door_status():
    """
    현재 도어/거래 상태 조회.

    Returns:
        DoorStatusResponse: 도어 및 거래 상태
    """
    global _door_payment_controller

    if _door_payment_controller is None:
        initialize_door_payment_controller()

    try:
        door_state = await _door_payment_controller._get_door_state()
        deadbolt_state = await _door_payment_controller._get_deadbolt_state()

        return DoorStatusResponse(
            current_state=_door_payment_controller.current_state.value,
            door_state=door_state.value,
            deadbolt_state=deadbolt_state.value,
        )

    except Exception as e:
        logger.error(f"Failed to get door status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/door/cancel")
async def cancel_door_transaction():
    """
    현재 진행 중인 도어 거래 취소.

    Returns:
        dict: 취소 결과
    """
    global _door_payment_controller

    if _door_payment_controller is None:
        raise HTTPException(status_code=400, detail="No active transaction")

    try:
        success = await _door_payment_controller.cancel_transaction()

        return {
            "success": success,
            "message": "Transaction cancelled" if success else "No active transaction to cancel",
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to cancel transaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/door/emergency-lock")
async def emergency_lock_door():
    """
    긴급 잠금 (데드볼트 즉시 잠금).

    Returns:
        dict: 잠금 결과
    """
    global _door_payment_controller

    if _door_payment_controller is None:
        initialize_door_payment_controller()

    try:
        success = await _door_payment_controller.emergency_lock()

        return {
            "success": success,
            "message": "Emergency lock executed" if success else "Emergency lock failed",
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Emergency lock failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
