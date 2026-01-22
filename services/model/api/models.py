"""
API Models for Model Service.

요청/응답 스키마 정의 (고급 기능).

엔드포인트:
- POST /api/judge/multi-zone: 다중 Zone 동시 판단
- POST /api/judge/with-history: 히스토리 기반 판단 (반환/연속픽업)
- GET /api/stats/recognition-rate: 인식률 통계
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from enum import Enum


# ===== Enums =====

class EventDirectionEnum(str, Enum):
    """이벤트 방향."""
    PICKUP = "pickup"
    RETURN = "return"
    MOVE = "move"


class JudgmentStatusEnum(str, Enum):
    """판단 상태."""
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"
    NO_DETECTION = "no_detection"


# ===== Multi-Zone Judgment =====

class ZoneDeltaItem(BaseModel):
    """Zone별 무게 변화량."""
    zone_id: int = Field(..., ge=0, le=4, description="Zone ID (0-4)")
    delta: float = Field(..., description="무게 변화량 (g)")
    timestamp: Optional[float] = Field(None, description="이벤트 시각")


class VisionCandidateItem(BaseModel):
    """Vision 후보군 아이템."""
    class_id: int = Field(..., description="상품 클래스 ID")
    class_name: str = Field(..., description="상품 이름")
    confidence: float = Field(..., ge=0.0, le=1.0, description="신뢰도")
    zone_id: Optional[int] = Field(None, description="감지된 Zone")


class MultiZoneJudgeRequest(BaseModel):
    """다중 Zone 판단 요청."""
    zone_deltas: List[ZoneDeltaItem] = Field(
        ...,
        description="Zone별 무게 변화량 리스트",
        min_length=1,
    )
    vision_candidates: Optional[List[VisionCandidateItem]] = Field(
        None,
        description="Vision 후보군 (없으면 자동 추론)",
    )
    check_cross_zone: bool = Field(
        True,
        description="Cross-Zone 이동 감지 여부",
    )
    door_open_duration: Optional[float] = Field(
        None,
        description="도어 오픈 시간 (초, drift 보정용)",
    )


class ZoneJudgmentResult(BaseModel):
    """Zone별 판단 결과."""
    zone_id: int
    products: List[dict] = Field(default_factory=list)
    total_price: int = 0
    status: JudgmentStatusEnum = JudgmentStatusEnum.NO_DETECTION
    confidence: float = 0.0
    weight_delta: float = 0.0
    weight_explained: float = 0.0


class CrossZoneMovementResult(BaseModel):
    """Cross-Zone 이동 감지 결과."""
    detected: bool = False
    source_zone: int = -1
    target_zone: int = -1
    weight: float = 0.0
    match_score: float = 0.0


class MultiZoneJudgeResponse(BaseModel):
    """다중 Zone 판단 응답."""
    success: bool
    zone_results: List[ZoneJudgmentResult]
    cross_zone_movement: Optional[CrossZoneMovementResult] = None
    total_price: int = 0
    timestamp: float


# ===== History-Based Judgment =====

class WeightEventItem(BaseModel):
    """무게 이벤트."""
    timestamp: float
    zone_id: int
    delta_weight: float
    direction: EventDirectionEnum = EventDirectionEnum.PICKUP
    product_id: Optional[int] = None
    product_name: Optional[str] = None


class CurrentJudgeRequest(BaseModel):
    """현재 판단 요청."""
    zone_id: int = Field(..., ge=0, le=4)
    delta_weight: float
    vision_candidates: Optional[List[VisionCandidateItem]] = None
    timestamp: Optional[float] = None


class HistoryJudgeRequest(BaseModel):
    """히스토리 기반 판단 요청."""
    current_request: CurrentJudgeRequest = Field(
        ...,
        description="현재 판단 요청",
    )
    recent_events: List[WeightEventItem] = Field(
        default_factory=list,
        description="최근 이벤트 히스토리",
    )
    check_return: bool = Field(
        True,
        description="반환 감지 여부",
    )
    check_rapid_pickup: bool = Field(
        True,
        description="연속 픽업 감지 여부",
    )
    settling_time: float = Field(
        1.0,
        description="안정화 대기 시간 (초)",
    )


class ReturnDetectionResult(BaseModel):
    """반환 감지 결과."""
    detected: bool = False
    original_pickup_timestamp: Optional[float] = None
    returned_product_id: Optional[int] = None
    returned_product_name: Optional[str] = None
    weight_match_score: float = 0.0


class RapidPickupResult(BaseModel):
    """연속 픽업 감지 결과."""
    detected: bool = False
    event_count: int = 0
    total_delta: float = 0.0
    duration: float = 0.0
    is_settled: bool = False


class HistoryJudgeResponse(BaseModel):
    """히스토리 기반 판단 응답."""
    success: bool
    products: List[dict] = Field(default_factory=list)
    total_price: int = 0
    status: JudgmentStatusEnum = JudgmentStatusEnum.NO_DETECTION
    confidence: float = 0.0
    return_detection: Optional[ReturnDetectionResult] = None
    rapid_pickup: Optional[RapidPickupResult] = None
    is_return_event: bool = False
    timestamp: float


# ===== Recognition Statistics =====

class ZoneStatistics(BaseModel):
    """Zone별 통계."""
    zone_id: int
    total_events: int = 0
    successful_judgments: int = 0
    failed_judgments: int = 0
    return_events: int = 0
    cross_zone_moves: int = 0
    recognition_rate: float = 0.0


class RecognitionRateResponse(BaseModel):
    """인식률 통계 응답."""
    overall_recognition_rate: float = Field(
        ...,
        description="전체 인식률 (0.0 ~ 1.0)",
    )
    total_events: int = Field(
        ...,
        description="총 이벤트 수",
    )
    successful_judgments: int = Field(
        ...,
        description="성공한 판단 수",
    )
    zone_statistics: List[ZoneStatistics] = Field(
        default_factory=list,
        description="Zone별 통계",
    )
    recent_period_hours: float = Field(
        24.0,
        description="통계 집계 기간 (시간)",
    )
    timestamp: float


# ===== Common Response Models =====

class ErrorResponse(BaseModel):
    """에러 응답."""
    success: bool = False
    error: str
    error_code: Optional[str] = None
    timestamp: float


# ===== Product Registration Models =====

class ProductRegisterRequest(BaseModel):
    """상품 등록 요청."""
    name: str = Field(..., min_length=1, max_length=100, description="상품 이름")
    category: str = Field(
        ...,
        description="카테고리 (beverage, snack, candy, food, dairy, health, etc)"
    )
    weight: float = Field(..., gt=0, description="단위 무게 (g)")
    price: int = Field(..., ge=0, description="가격 (원)")
    barcode: Optional[str] = Field(
        None,
        min_length=8,
        max_length=14,
        description="바코드 (선택, 8-14자리)"
    )
    stock: int = Field(0, ge=0, description="초기 재고 수량")


class ProductRegisterResponse(BaseModel):
    """상품 등록 응답."""
    success: bool = True
    product_id: int = Field(..., description="등록된 상품 ID")
    name: str = Field(..., description="상품 이름")
    status: str = Field("registered", description="상태")
    timestamp: float


class ProductUpdateRequest(BaseModel):
    """상품 수정 요청."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = None
    weight: Optional[float] = Field(None, gt=0)
    price: Optional[int] = Field(None, ge=0)
    barcode: Optional[str] = Field(None, min_length=8, max_length=14)
    stock: Optional[int] = Field(None, ge=0)


class ProductUpdateResponse(BaseModel):
    """상품 수정 응답."""
    success: bool = True
    product_id: int
    message: str
    timestamp: float


class ProductDeleteResponse(BaseModel):
    """상품 삭제 응답."""
    success: bool = True
    product_id: int
    message: str
    timestamp: float


class ImageUploadResponse(BaseModel):
    """이미지 업로드 응답."""
    success: bool = True
    product_id: int
    camera_id: int
    saved_count: int = Field(..., description="저장된 이미지 수")
    save_path: str = Field(..., description="저장 경로")
    total_images: int = Field(..., description="상품의 총 이미지 수")
    timestamp: float


class ProductExportResponse(BaseModel):
    """상품 전체 목록 내보내기 응답."""
    success: bool = True
    products: List[dict] = Field(..., description="상품 목록")
    count: int = Field(..., description="상품 수")
    timestamp: float


class ProductSearchRequest(BaseModel):
    """상품 검색 요청."""
    query: str = Field(..., min_length=1, description="검색어")
    limit: int = Field(10, ge=1, le=100, description="최대 결과 수")
