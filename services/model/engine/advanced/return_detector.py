"""
Return Detector.

상품 픽업 후 반납 감지 (시나리오 5).

핵심 기능:
1. 최근 픽업 이벤트 추적
2. 양수 무게 변화와 픽업 이벤트 매칭
3. 시간 윈도우 기반 반납 판정
4. 결제 취소 플래그 생성

사용 예시:
    detector = ReturnDetector(match_tolerance=0.15)
    detector.record_pickup(zone_id=0, weight=365.0, product_id=26)
    result = detector.check_return(zone_id=0, positive_delta=365.0)
    if result.is_return:
        # 결제 취소 처리
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class PickupEvent:
    """
    픽업 이벤트 기록.

    Attributes:
        event_id: 이벤트 ID
        timestamp: 픽업 시각
        zone_id: Zone ID
        weight: 픽업 무게 (양수)
        product_id: 상품 ID (옵션)
        product_name: 상품 이름 (옵션)
        count: 개수 (옵션)
        returned: 반납 여부
        return_timestamp: 반납 시각
    """
    event_id: str
    timestamp: float
    zone_id: int
    weight: float
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    count: int = 1
    returned: bool = False
    return_timestamp: Optional[float] = None

    @property
    def age(self) -> float:
        """이벤트 발생 후 경과 시간 (초)."""
        return time.time() - self.timestamp

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "zone_id": self.zone_id,
            "weight": round(self.weight, 1),
            "product_id": self.product_id,
            "product_name": self.product_name,
            "count": self.count,
            "returned": self.returned,
            "return_timestamp": self.return_timestamp,
            "age": round(self.age, 1),
        }


@dataclass
class ReturnResult:
    """
    반납 감지 결과.

    Attributes:
        is_return: 반납 여부
        pickup_event: 원래 픽업 이벤트
        weight_delta: 반납 무게 변화량
        match_score: 무게 매칭 점수 (0.0 ~ 1.0)
        should_cancel_payment: 결제 취소 권장 여부
        return_type: 반납 유형 (same_position, horizontal_move, cross_shelf)
    """
    is_return: bool = False
    pickup_event: Optional[PickupEvent] = None
    weight_delta: float = 0.0
    match_score: float = 0.0
    should_cancel_payment: bool = False
    return_type: str = "none"

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "is_return": self.is_return,
            "pickup_event": self.pickup_event.to_dict() if self.pickup_event else None,
            "weight_delta": round(self.weight_delta, 1),
            "match_score": round(self.match_score, 3),
            "should_cancel_payment": self.should_cancel_payment,
            "return_type": self.return_type,
        }


class ReturnDetector:
    """
    상품 반납 감지기.

    픽업 후 반납을 감지하고 결제 취소를 권장합니다.

    Attributes:
        match_tolerance: 무게 매칭 허용 오차 (비율)
        return_window: 반납 감지 시간 윈도우 (초)
        cross_zone_enabled: Cross-Zone 반납 허용 여부
        max_history: 최대 픽업 기록 수
    """

    def __init__(
        self,
        match_tolerance: float = 0.15,
        return_window: float = 30.0,
        cross_zone_enabled: bool = True,
        max_history: int = 50,
    ):
        """
        감지기 초기화.

        Args:
            match_tolerance: 무게 매칭 허용 오차 (비율)
            return_window: 반납 감지 시간 윈도우 (초)
            cross_zone_enabled: Cross-Zone 반납 허용 여부
            max_history: 최대 픽업 기록 수
        """
        self.match_tolerance = match_tolerance
        self.return_window = return_window
        self.cross_zone_enabled = cross_zone_enabled
        self.max_history = max_history

        self.recent_pickups: List[PickupEvent] = []
        self._event_counter = 0

    def _generate_event_id(self) -> str:
        """이벤트 ID 생성."""
        self._event_counter += 1
        return f"pickup_{int(time.time())}_{self._event_counter}"

    def record_pickup(
        self,
        zone_id: int,
        weight: float,
        product_id: Optional[int] = None,
        product_name: Optional[str] = None,
        count: int = 1,
    ) -> PickupEvent:
        """
        픽업 이벤트 기록.

        Args:
            zone_id: Zone ID
            weight: 픽업 무게 (양수)
            product_id: 상품 ID
            product_name: 상품 이름
            count: 개수

        Returns:
            생성된 PickupEvent
        """
        event = PickupEvent(
            event_id=self._generate_event_id(),
            timestamp=time.time(),
            zone_id=zone_id,
            weight=abs(weight),  # 양수로 저장
            product_id=product_id,
            product_name=product_name,
            count=count,
        )

        self.recent_pickups.append(event)

        # 히스토리 크기 제한
        if len(self.recent_pickups) > self.max_history:
            self.recent_pickups = self.recent_pickups[-self.max_history:]

        logger.debug(
            f"Pickup recorded: zone={zone_id}, weight={weight:.1f}g, "
            f"product={product_name or product_id}"
        )

        return event

    def check_return(
        self,
        zone_id: int,
        positive_delta: float,
        timestamp: Optional[float] = None,
    ) -> ReturnResult:
        """
        반납 여부 확인.

        양수 무게 변화가 최근 픽업과 매칭되는지 확인합니다.

        Args:
            zone_id: Zone ID
            positive_delta: 양수 무게 변화량 (g)
            timestamp: 현재 시각 (None이면 현재 시간)

        Returns:
            ReturnResult
        """
        if positive_delta <= 0:
            return ReturnResult(is_return=False)

        current_time = timestamp or time.time()
        return_weight = abs(positive_delta)

        best_match: Optional[PickupEvent] = None
        best_score = 0.0
        return_type = "none"

        for pickup in reversed(self.recent_pickups):
            # 시간 윈도우 체크
            if current_time - pickup.timestamp > self.return_window:
                continue

            # 이미 반납된 이벤트 스킵
            if pickup.returned:
                continue

            # Zone 체크
            same_zone = pickup.zone_id == zone_id
            if not same_zone and not self.cross_zone_enabled:
                continue

            # 무게 매칭 점수 계산
            weight_diff = abs(pickup.weight - return_weight)
            max_diff = pickup.weight * self.match_tolerance

            if weight_diff <= max_diff:
                score = 1.0 - (weight_diff / pickup.weight) if pickup.weight > 0 else 0

                # 같은 Zone이면 보너스
                if same_zone:
                    score = min(score + 0.1, 1.0)
                    rtype = "same_position"
                else:
                    # Cross-Zone 반납
                    zone_diff = abs(pickup.zone_id - zone_id)
                    if zone_diff == 1:
                        rtype = "horizontal_move"
                    else:
                        rtype = "cross_shelf"

                if score > best_score:
                    best_score = score
                    best_match = pickup
                    return_type = rtype

        if best_match and best_score >= 0.7:  # 최소 매칭 점수
            # 반납 처리
            best_match.returned = True
            best_match.return_timestamp = current_time

            logger.info(
                f"Return detected: zone={zone_id}, weight={return_weight:.1f}g, "
                f"original={best_match.weight:.1f}g, type={return_type}, "
                f"score={best_score:.3f}"
            )

            return ReturnResult(
                is_return=True,
                pickup_event=best_match,
                weight_delta=positive_delta,
                match_score=best_score,
                should_cancel_payment=True,
                return_type=return_type,
            )

        return ReturnResult(
            is_return=False,
            weight_delta=positive_delta,
        )

    def get_pending_pickups(
        self,
        zone_id: Optional[int] = None,
    ) -> List[PickupEvent]:
        """
        미반납 픽업 이벤트 목록.

        Args:
            zone_id: Zone ID (None이면 전체)

        Returns:
            PickupEvent 리스트
        """
        current_time = time.time()
        pending = []

        for pickup in self.recent_pickups:
            # 시간 윈도우 내 미반납 이벤트만
            if pickup.returned:
                continue
            if current_time - pickup.timestamp > self.return_window:
                continue
            if zone_id is not None and pickup.zone_id != zone_id:
                continue
            pending.append(pickup)

        return pending

    def get_zone_balance(self, zone_id: int) -> float:
        """
        Zone의 미반납 픽업 총 무게.

        Args:
            zone_id: Zone ID

        Returns:
            미반납 총 무게 (g)
        """
        pending = self.get_pending_pickups(zone_id)
        return sum(p.weight for p in pending)

    def clear_expired(self) -> int:
        """
        만료된 픽업 이벤트 정리.

        Returns:
            삭제된 이벤트 수
        """
        current_time = time.time()
        original_count = len(self.recent_pickups)

        self.recent_pickups = [
            p for p in self.recent_pickups
            if current_time - p.timestamp <= self.return_window * 2
        ]

        removed = original_count - len(self.recent_pickups)
        if removed > 0:
            logger.debug(f"Cleared {removed} expired pickup events")

        return removed

    def reset_zone(self, zone_id: int):
        """
        특정 Zone의 픽업 기록 초기화.

        Args:
            zone_id: Zone ID
        """
        self.recent_pickups = [
            p for p in self.recent_pickups
            if p.zone_id != zone_id
        ]
        logger.info(f"Zone {zone_id} pickup history cleared")

    def to_dict(self) -> dict:
        """상태 딕셔너리 변환."""
        return {
            "match_tolerance": self.match_tolerance,
            "return_window": self.return_window,
            "total_pickups": len(self.recent_pickups),
            "pending_count": len(self.get_pending_pickups()),
            "recent_pickups": [p.to_dict() for p in self.recent_pickups[-5:]],
        }
