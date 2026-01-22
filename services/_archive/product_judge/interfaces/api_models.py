"""
API Models for Node.js Interface.

Pydantic 모델 정의 - FastAPI 자동 문서화 지원.

Request/Response 형식:
- JudgeRequest: 상품 판단 요청
- JudgeResponse: 상품 판단 응답 (Node.js 전달용)
- TestRequest: 테스트용 요청 (로드셀 없이)
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class JudgmentStatusEnum(str, Enum):
    """상품 판단 상태."""
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"
    NO_DETECTION = "no_detection"


# ========== Detection 관련 ==========

class DetectionInput(BaseModel):
    """YOLO 감지 입력."""
    xyxy: List[float] = Field(..., description="Bounding box [x1, y1, x2, y2]")
    conf: float = Field(..., ge=0, le=1, description="Confidence")
    cls: int = Field(..., ge=0, description="Class ID")
    name: str = Field(..., description="Class name")

    class Config:
        json_schema_extra = {
            "example": {
                "xyxy": [258.72, 47.65, 315.12, 113.97],
                "conf": 0.788,
                "cls": 0,
                "name": "hand"
            }
        }


# ========== Request 모델 ==========

class JudgeRequest(BaseModel):
    """
    상품 판단 요청.

    실제 시스템에서 사용:
    - snapshot_folder: 스냅샷 이미지 경로
    - loadcell_weights: 현재 로드셀 무게
    - baseline_weights: 기준 무게
    """
    snapshot_folder: str = Field(..., description="스냅샷 이미지 폴더 경로")
    loadcell_weights: List[float] = Field(
        ...,
        min_items=10,
        max_items=10,
        description="10채널 로드셀 현재 무게 (g)"
    )
    baseline_weights: List[float] = Field(
        ...,
        min_items=10,
        max_items=10,
        description="10채널 로드셀 기준 무게 (g)"
    )
    zone_id: Optional[int] = Field(None, ge=0, le=4, description="Zone ID (0-4)")

    class Config:
        json_schema_extra = {
            "example": {
                "snapshot_folder": "/data/260116_1200/",
                "loadcell_weights": [500, 500, 0, 0, 0, 0, 0, 0, 0, 0],
                "baseline_weights": [865, 500, 0, 0, 0, 0, 0, 0, 0, 0],
                "zone_id": 0
            }
        }


class TestRequest(BaseModel):
    """
    테스트용 요청 (로드셀 연결 없이 테스트).

    Node.js 전체 결제 프로세스 점검용.
    직접 YOLO 감지 결과와 무게 변화량 입력.
    """
    detections: List[DetectionInput] = Field(
        ...,
        description="YOLO 감지 결과 리스트"
    )
    delta_weight: float = Field(
        ...,
        description="무게 변화량 (g, 음수=제거)"
    )
    zone_id: Optional[int] = Field(None, ge=0, le=4, description="Zone ID")
    use_hand_filter: bool = Field(True, description="손 근접 필터링 사용 여부")

    class Config:
        json_schema_extra = {
            "example": {
                "detections": [
                    {"xyxy": [258.72, 47.65, 315.12, 113.97], "conf": 0.788, "cls": 0, "name": "hand"},
                    {"xyxy": [257.67, 75.54, 284.33, 110.22], "conf": 0.492, "cls": 26, "name": "chickenmayo_rice"},
                ],
                "delta_weight": -365.0,
                "zone_id": 0,
                "use_hand_filter": True
            }
        }


class SimulateRequest(BaseModel):
    """
    시뮬레이션 요청 (완전 테스트용).

    직접 class_id와 개수를 지정하여 결과 생성.
    """
    product_id: int = Field(..., ge=1, description="상품 ID")
    count: int = Field(..., ge=1, le=10, description="개수")
    confidence: float = Field(0.8, ge=0, le=1, description="Vision 신뢰도")

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": 26,
                "count": 1,
                "confidence": 0.85
            }
        }


# ========== Response 모델 ==========

class ProductOutput(BaseModel):
    """개별 상품 응답."""
    productId: int = Field(..., description="상품 ID")
    name: str = Field(..., description="상품 이름")
    count: int = Field(..., description="개수")
    unitPrice: int = Field(..., description="단가 (원)")
    totalPrice: int = Field(..., description="총 가격 (원)")
    confidence: float = Field(..., description="신뢰도 (0.0-1.0)")

    class Config:
        json_schema_extra = {
            "example": {
                "productId": 26,
                "name": "chickenmayo_rice",
                "count": 1,
                "unitPrice": 3500,
                "totalPrice": 3500,
                "confidence": 0.85
            }
        }


class WeightInfo(BaseModel):
    """무게 정보."""
    delta: float = Field(..., description="무게 변화량 (g)")
    explained: float = Field(..., description="설명된 무게 (g)")
    residual: float = Field(..., description="잔여 무게 (g)")


class JudgeResponse(BaseModel):
    """
    상품 판단 응답 (Node.js 전달용).

    success=True면 결제 진행 가능.
    """
    success: bool = Field(..., description="판단 성공 여부")
    products: List[ProductOutput] = Field(..., description="판단된 상품 리스트")
    totalPrice: int = Field(..., description="총 결제 금액 (원)")
    status: JudgmentStatusEnum = Field(..., description="판단 상태")
    confidence: float = Field(..., description="전체 신뢰도 (0.0-1.0)")
    weightInfo: WeightInfo = Field(..., description="무게 정보")
    productCount: int = Field(..., description="총 상품 개수")
    isRemoval: bool = Field(..., description="상품 제거 여부")
    timestamp: float = Field(..., description="판단 시각 (Unix timestamp)")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "products": [
                    {
                        "productId": 26,
                        "name": "chickenmayo_rice",
                        "count": 1,
                        "unitPrice": 3500,
                        "totalPrice": 3500,
                        "confidence": 0.85
                    }
                ],
                "totalPrice": 3500,
                "status": "complete",
                "confidence": 0.85,
                "weightInfo": {
                    "delta": -365.0,
                    "explained": 365.0,
                    "residual": 0.0
                },
                "productCount": 1,
                "isRemoval": True,
                "timestamp": 1737046800.123
            }
        }


class HealthResponse(BaseModel):
    """헬스 체크 응답."""
    status: str = Field("ok", description="서비스 상태")
    version: str = Field(..., description="서비스 버전")
    product_count: int = Field(..., description="등록된 상품 수")


class ErrorResponse(BaseModel):
    """에러 응답."""
    success: bool = Field(False)
    error: str = Field(..., description="에러 메시지")
    detail: Optional[str] = Field(None, description="상세 정보")


# ========== Advanced Scenario Models (시나리오 4-8) ==========

class ZoneDelta(BaseModel):
    """Zone별 무게 변화."""
    zone_id: int = Field(..., ge=0, le=4, description="Zone ID (0-4)")
    delta: float = Field(..., description="무게 변화량 (g)")


class WeightEventInput(BaseModel):
    """무게 이벤트 입력."""
    timestamp: float = Field(..., description="이벤트 시각 (Unix timestamp)")
    zone_id: int = Field(..., ge=0, le=4, description="Zone ID")
    delta: float = Field(..., description="무게 변화량 (g)")
    direction: str = Field("pickup", description="이벤트 방향 (pickup/return)")


class MultiZoneJudgeRequest(BaseModel):
    """
    다중 Zone 동시 판단 요청 (시나리오 4, 6).

    다중 사용자 동시 취출 또는 Zone 간 상품 이동 처리.
    """
    zone_deltas: List[ZoneDelta] = Field(
        ...,
        description="Zone별 무게 변화 리스트"
    )
    detections: List[DetectionInput] = Field(
        ...,
        description="YOLO 감지 결과"
    )
    door_open_duration: float = Field(
        0.0,
        ge=0,
        description="도어 오픈 시간 (초) - 시나리오 7용"
    )
    check_cross_zone: bool = Field(
        True,
        description="Cross-Zone 이동 감지 여부"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "zone_deltas": [
                    {"zone_id": 0, "delta": -365.0},
                    {"zone_id": 2, "delta": -130.0}
                ],
                "detections": [
                    {"xyxy": [100, 100, 150, 150], "conf": 0.9, "cls": 0, "name": "hand"},
                    {"xyxy": [300, 100, 350, 150], "conf": 0.85, "cls": 0, "name": "hand"},
                    {"xyxy": [110, 110, 160, 160], "conf": 0.8, "cls": 26, "name": "chickenmayo_rice"},
                    {"xyxy": [310, 110, 360, 160], "conf": 0.75, "cls": 9, "name": "vita500"}
                ],
                "door_open_duration": 0.0
            }
        }


class JudgeWithHistoryRequest(BaseModel):
    """
    이전 이벤트 기록 포함 판단 요청 (시나리오 5, 8).

    반납 감지 및 연속 취출 처리.
    """
    current_request: TestRequest = Field(
        ...,
        description="현재 판단 요청"
    )
    recent_events: List[WeightEventInput] = Field(
        default_factory=list,
        description="최근 무게 이벤트 히스토리"
    )
    check_return: bool = Field(
        True,
        description="반납 감지 여부"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "current_request": {
                    "detections": [],
                    "delta_weight": 365.0,
                    "zone_id": 0
                },
                "recent_events": [
                    {"timestamp": 1737046790, "zone_id": 0, "delta": -365.0, "direction": "pickup"}
                ],
                "check_return": True
            }
        }


class MultiZoneResult(BaseModel):
    """Zone별 판단 결과."""
    zone_id: int = Field(..., description="Zone ID")
    products: List[ProductOutput] = Field(..., description="판단된 상품")
    total_price: int = Field(..., description="총 가격")
    confidence: float = Field(..., description="신뢰도")
    status: JudgmentStatusEnum = Field(..., description="판단 상태")


class CrossZoneMovement(BaseModel):
    """Cross-Zone 이동 정보."""
    detected: bool = Field(..., description="이동 감지 여부")
    source_zone: int = Field(-1, description="출발 Zone")
    target_zone: int = Field(-1, description="도착 Zone")
    weight: float = Field(0.0, description="이동 무게 (g)")
    movement_type: str = Field("none", description="이동 유형")


class MultiZoneJudgeResponse(BaseModel):
    """
    다중 Zone 판단 응답.
    """
    success: bool = Field(..., description="판단 성공 여부")
    zone_results: List[MultiZoneResult] = Field(..., description="Zone별 결과")
    total_price: int = Field(..., description="전체 총 가격")
    cross_zone_movement: Optional[CrossZoneMovement] = Field(
        None,
        description="Cross-Zone 이동 정보"
    )
    person_count: int = Field(1, description="추정 인원 수")
    timestamp: float = Field(..., description="판단 시각")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "zone_results": [
                    {
                        "zone_id": 0,
                        "products": [{"productId": 26, "name": "chickenmayo_rice", "count": 1, "unitPrice": 3500, "totalPrice": 3500, "confidence": 0.85}],
                        "total_price": 3500,
                        "confidence": 0.85,
                        "status": "complete"
                    }
                ],
                "total_price": 3500,
                "person_count": 2,
                "timestamp": 1737046800.123
            }
        }


class ReturnDetectionResult(BaseModel):
    """반납 감지 결과."""
    is_return: bool = Field(..., description="반납 여부")
    original_weight: Optional[float] = Field(None, description="원래 픽업 무게")
    return_weight: float = Field(..., description="반납 무게")
    match_score: float = Field(0.0, description="매칭 점수")
    should_cancel_payment: bool = Field(False, description="결제 취소 권장")
    return_type: str = Field("none", description="반납 유형")


class JudgeWithHistoryResponse(BaseModel):
    """
    이벤트 히스토리 포함 판단 응답.
    """
    judgment_result: JudgeResponse = Field(..., description="기본 판단 결과")
    return_detection: Optional[ReturnDetectionResult] = Field(
        None,
        description="반납 감지 결과"
    )
    is_rapid_pickup: bool = Field(False, description="연속 취출 여부")
    event_count: int = Field(1, description="이벤트 수")

    class Config:
        json_schema_extra = {
            "example": {
                "judgment_result": {
                    "success": False,
                    "products": [],
                    "totalPrice": 0,
                    "status": "no_detection",
                    "confidence": 0.0,
                    "weightInfo": {"delta": 365.0, "explained": 0.0, "residual": 365.0},
                    "productCount": 0,
                    "isRemoval": False,
                    "timestamp": 1737046800.123
                },
                "return_detection": {
                    "is_return": True,
                    "original_weight": 365.0,
                    "return_weight": 365.0,
                    "match_score": 0.95,
                    "should_cancel_payment": True,
                    "return_type": "same_position"
                },
                "is_rapid_pickup": False,
                "event_count": 1
            }
        }


class RecognitionStats(BaseModel):
    """인식률 통계."""
    total_tests: int = Field(..., description="총 테스트 수")
    successful: int = Field(..., description="성공 수")
    failed: int = Field(..., description="실패 수")
    recognition_rate: float = Field(..., description="인식률 (%)")
    avg_confidence: float = Field(..., description="평균 신뢰도")
    avg_processing_time_ms: float = Field(..., description="평균 처리 시간 (ms)")
