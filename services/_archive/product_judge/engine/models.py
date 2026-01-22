"""
Data Models for Product Judgment Service.

상품 판단 서비스의 핵심 데이터 모델 정의.

핵심 플로우:
1. Detection: YOLO에서 감지된 객체 (손/상품)
2. EnsembleResult: Top+Side 카메라 앙상블 결과
3. CountEstimate: 무게 기반 개수 추정
4. ProductJudgment: 개별 상품 판단 결과
5. JudgmentResult: 최종 상품 판단 결과 (Node.js 전달용)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
import time


class JudgmentStatus(Enum):
    """상품 판단 상태."""

    COMPLETE = "complete"         # 무게가 완전히 설명됨
    PARTIAL = "partial"           # 일부만 설명됨 (잔여 무게 있음)
    UNCERTAIN = "uncertain"       # 확신할 수 없음 (신뢰도 낮음)
    NO_DETECTION = "no_detection" # 감지된 상품 없음


@dataclass
class Detection:
    """
    YOLO 감지 결과.

    Attributes:
        class_id: 클래스 ID (0=hand, 1+=products)
        class_name: 클래스 이름
        confidence: 신뢰도 (0.0 ~ 1.0)
        bbox: Bounding box [x1, y1, x2, y2]
    """
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2

    @property
    def center(self) -> Tuple[float, float]:
        """Bounding box 중심점."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    @property
    def area(self) -> float:
        """Bounding box 면적."""
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)

    @property
    def is_hand(self) -> bool:
        """손인지 여부 (class_id == 0)."""
        return self.class_id == 0

    def distance_to(self, other: "Detection") -> float:
        """다른 Detection과의 중심점 거리."""
        cx1, cy1 = self.center
        cx2, cy2 = other.center
        return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
            "bbox": list(self.bbox),
            "center": list(self.center),
        }


@dataclass
class EnsembleResult:
    """
    Multi-View Ensemble 결과.

    Top + Side 카메라에서 앙상블된 상품 후보.

    Attributes:
        class_id: 클래스 ID
        class_name: 클래스 이름
        top_confidence: Top 카메라 신뢰도
        side_confidence: Side 카메라 신뢰도
        combined_confidence: 앙상블 결합 신뢰도
        vote_count: 양쪽 합의 (2=양쪽, 1=한쪽)
    """
    class_id: int
    class_name: str
    top_confidence: float
    side_confidence: float
    combined_confidence: float
    vote_count: int = 1  # 1 or 2 (양쪽 합의)

    @property
    def is_consensus(self) -> bool:
        """양쪽 카메라에서 합의되었는지."""
        return self.vote_count == 2

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "top_confidence": round(self.top_confidence, 4),
            "side_confidence": round(self.side_confidence, 4),
            "combined_confidence": round(self.combined_confidence, 4),
            "vote_count": self.vote_count,
            "is_consensus": self.is_consensus,
        }


@dataclass
class CountEstimate:
    """
    무게 기반 개수 추정 결과.

    Attributes:
        product_id: 상품 ID
        product_name: 상품 이름
        count: 추정 개수
        unit_weight: 단위 무게 (g)
        expected_weight: 예상 무게 (unit_weight * count)
        actual_weight: 실제 무게 변화량 (절대값)
        match_score: 매칭 점수 (0.0 ~ 1.0)
        vision_confidence: Vision 신뢰도
        validated: 허용 오차 내 검증 여부
    """
    product_id: int
    product_name: str
    count: int
    unit_weight: float
    expected_weight: float
    actual_weight: float
    match_score: float
    vision_confidence: float
    validated: bool

    @property
    def weight_error(self) -> float:
        """무게 오차 (절대값)."""
        return abs(self.actual_weight - self.expected_weight)

    @property
    def error_rate(self) -> float:
        """오차율 (0.0 ~ 1.0)."""
        if self.expected_weight == 0:
            return 1.0
        return self.weight_error / self.expected_weight

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "count": self.count,
            "unit_weight": round(self.unit_weight, 1),
            "expected_weight": round(self.expected_weight, 1),
            "actual_weight": round(self.actual_weight, 1),
            "weight_error": round(self.weight_error, 1),
            "error_rate": round(self.error_rate, 4),
            "match_score": round(self.match_score, 4),
            "vision_confidence": round(self.vision_confidence, 4),
            "validated": self.validated,
        }


@dataclass
class ProductJudgment:
    """
    개별 상품 판단 결과.

    Node.js로 전달되는 개별 상품 정보.

    Attributes:
        product_id: 상품 ID
        name: 상품 이름
        count: 개수
        unit_price: 단가 (원)
        total_price: 총 가격 (원)
        confidence: 신뢰도 (0.0 ~ 1.0)
        unit_weight: 단위 무게 (g)
    """
    product_id: int
    name: str
    count: int
    unit_price: int
    total_price: int
    confidence: float
    unit_weight: float = 0.0

    def to_dict(self) -> dict:
        """딕셔너리 변환 (Node.js 형식)."""
        return {
            "productId": self.product_id,
            "name": self.name,
            "count": self.count,
            "unitPrice": self.unit_price,
            "totalPrice": self.total_price,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class JudgmentResult:
    """
    최종 상품 판단 결과.

    Node.js Orchestrator로 전달되는 전체 결과.

    Attributes:
        products: 판단된 상품 리스트
        total_price: 총 가격 (원)
        confidence: 전체 신뢰도 (0.0 ~ 1.0)
        status: 판단 상태 (complete/partial/uncertain/no_detection)
        weight_delta: 무게 변화량 (음수 = 제거)
        weight_explained: 설명된 무게 (양수)
        weight_residual: 잔여 무게 (설명 안 됨)
        timestamp: 판단 시각 (Unix timestamp)
    """
    products: List[ProductJudgment] = field(default_factory=list)
    total_price: int = 0
    confidence: float = 0.0
    status: JudgmentStatus = JudgmentStatus.NO_DETECTION
    weight_delta: float = 0.0
    weight_explained: float = 0.0
    weight_residual: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def is_removal(self) -> bool:
        """상품 제거 여부 (무게 감소)."""
        return self.weight_delta < 0

    @property
    def is_success(self) -> bool:
        """성공적인 판단 여부."""
        return self.status in [JudgmentStatus.COMPLETE, JudgmentStatus.PARTIAL]

    @property
    def product_count(self) -> int:
        """총 상품 개수."""
        return sum(p.count for p in self.products)

    def to_node_response(self) -> dict:
        """
        Node.js 서버 응답 형식으로 변환.

        Returns:
            {
                "success": bool,
                "products": [...],
                "totalPrice": int,
                "status": str,
                "confidence": float,
                "weightInfo": {...},
                "timestamp": float,
            }
        """
        return {
            "success": self.is_success,
            "products": [p.to_dict() for p in self.products],
            "totalPrice": self.total_price,
            "status": self.status.value,
            "confidence": round(self.confidence, 2),
            "weightInfo": {
                "delta": round(self.weight_delta, 1),
                "explained": round(self.weight_explained, 1),
                "residual": round(self.weight_residual, 1),
            },
            "productCount": self.product_count,
            "isRemoval": self.is_removal,
            "timestamp": self.timestamp,
        }

    def to_dict(self) -> dict:
        """딕셔너리 변환 (내부용)."""
        return {
            "products": [p.to_dict() for p in self.products],
            "total_price": self.total_price,
            "confidence": self.confidence,
            "status": self.status.value,
            "weight_delta": self.weight_delta,
            "weight_explained": self.weight_explained,
            "weight_residual": self.weight_residual,
            "timestamp": self.timestamp,
        }


@dataclass
class ProductInfo:
    """
    상품 정보 (데이터베이스용).

    Attributes:
        product_id: 상품 ID
        name: 상품 이름
        category: 카테고리
        weight: 단위 무게 (g)
        price: 가격 (원)
    """
    product_id: int
    name: str
    category: str
    weight: float  # grams
    price: int     # won

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "weight": self.weight,
            "price": self.price,
        }


@dataclass
class JudgmentRequest:
    """
    상품 판단 요청.

    Node.js에서 전달받는 요청 데이터.

    Attributes:
        snapshot_folder: 스냅샷 이미지 폴더 경로
        loadcell_weights: 10채널 로드셀 현재 값
        baseline_weights: 10채널 기준 무게
        zone_id: Zone ID (옵션, None이면 자동 감지)
        timestamp: 요청 시각
    """
    snapshot_folder: str
    loadcell_weights: List[float]
    baseline_weights: List[float]
    zone_id: Optional[int] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def weight_deltas(self) -> List[float]:
        """채널별 무게 변화량."""
        return [
            curr - base
            for curr, base in zip(self.loadcell_weights, self.baseline_weights)
        ]

    @property
    def total_delta(self) -> float:
        """총 무게 변화량."""
        return sum(self.weight_deltas)

    def get_zone_delta(self, zone_id: int) -> float:
        """
        특정 Zone의 무게 변화량.

        Zone 매핑:
        - Zone 0: Ch 1,2 (index 0,1)
        - Zone 1: Ch 3,4 (index 2,3)
        - Zone 2: Ch 5,6 (index 4,5)
        - Zone 3: Ch 7,8 (index 6,7)
        - Zone 4: Ch 9,10 (index 8,9)
        """
        start_idx = zone_id * 2
        return sum(self.weight_deltas[start_idx:start_idx + 2])

    def detect_active_zone(self, threshold: float = 5.0) -> Optional[int]:
        """
        무게 변화가 감지된 Zone 자동 탐지.

        Args:
            threshold: 변화 감지 임계값 (g)

        Returns:
            Zone ID 또는 None
        """
        for zone_id in range(5):
            delta = abs(self.get_zone_delta(zone_id))
            if delta > threshold:
                return zone_id
        return None

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "snapshot_folder": self.snapshot_folder,
            "loadcell_weights": self.loadcell_weights,
            "baseline_weights": self.baseline_weights,
            "weight_deltas": self.weight_deltas,
            "total_delta": self.total_delta,
            "zone_id": self.zone_id,
            "timestamp": self.timestamp,
        }
