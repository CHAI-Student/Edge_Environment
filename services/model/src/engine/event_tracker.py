"""
Event Tracker.

Zone별 이벤트 상태 추적 및 관리.

핵심 기능:
1. 무게 변화 이벤트 기록 (pickup/return/move)
2. 이벤트 안정화 감지 (settling_time 기반)
3. 반납 이벤트 매칭 (최근 픽업과 비교)
4. 이벤트 히스토리 관리
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import time
import logging

from config import get_enabled_zones

logger = logging.getLogger(__name__)


# ========== Event Direction & Weight Event (for advanced modules) ==========

class EventDirection(str, Enum):
    """이벤트 방향."""
    PICKUP = "pickup"    # 상품 제거 (무게 감소)
    RETURN = "return"    # 상품 반납 (무게 증가)
    MOVE = "move"        # 상품 이동 (다른 Zone으로)


@dataclass
class WeightEvent:
    """
    무게 변화 이벤트.

    Attributes:
        timestamp: 이벤트 발생 시각 (Unix timestamp)
        zone_id: Zone ID (0-4)
        delta_weight: 무게 변화량 (음수=제거, 양수=추가)
        direction: 이벤트 방향 (pickup/return/move)
        settled: 안정화 여부
        matched_event_id: 매칭된 이벤트 ID (반납 시)
        product_id: 판단된 상품 ID (옵션)
        product_name: 판단된 상품 이름 (옵션)
        count: 판단된 개수 (옵션)
    """
    timestamp: float
    zone_id: int
    delta_weight: float
    direction: EventDirection = EventDirection.PICKUP
    settled: bool = False
    matched_event_id: Optional[str] = None
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    count: Optional[int] = None
    event_id: str = field(default_factory=lambda: f"evt_{int(time.time() * 1000)}")

    @property
    def abs_weight(self) -> float:
        """절대 무게 변화량."""
        return abs(self.delta_weight)

    @property
    def is_pickup(self) -> bool:
        """픽업 이벤트 여부."""
        return self.direction == EventDirection.PICKUP

    @property
    def is_return(self) -> bool:
        """반납 이벤트 여부."""
        return self.direction == EventDirection.RETURN

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
            "delta_weight": round(self.delta_weight, 1),
            "direction": self.direction.value,
            "settled": self.settled,
            "matched_event_id": self.matched_event_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "count": self.count,
        }


@dataclass
class ReturnResult:
    """
    반납 감지 결과.

    Attributes:
        is_return: 반납 여부
        original_event: 원래 픽업 이벤트
        return_event: 반납 이벤트
        weight_match_score: 무게 매칭 점수 (0.0 ~ 1.0)
        should_cancel: 결제 취소 여부
    """
    is_return: bool
    original_event: Optional[WeightEvent] = None
    return_event: Optional[WeightEvent] = None
    weight_match_score: float = 0.0
    should_cancel: bool = False

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "is_return": self.is_return,
            "original_event": self.original_event.to_dict() if self.original_event else None,
            "return_event": self.return_event.to_dict() if self.return_event else None,
            "weight_match_score": round(self.weight_match_score, 3),
            "should_cancel": self.should_cancel,
        }


# ========== Zone Event State (for zone-based tracking) ==========

class EventState(Enum):
    """이벤트 상태."""
    IDLE = "idle"
    ACTIVE = "active"  # 무게 변화 감지됨, 카메라 활성화
    PROCESSING = "processing"  # Vision 추론 중
    COMPLETED = "completed"  # 판단 완료
    TIMEOUT = "timeout"  # 타임아웃


@dataclass
class ZoneEvent:
    """Zone별 이벤트."""
    zone_id: int
    state: EventState = EventState.IDLE
    start_time: Optional[float] = None
    delta_weight: float = 0.0
    last_update_time: Optional[float] = None
    stable_since: Optional[float] = None  # 안정화 시작 시각
    judgment_result: Optional[dict] = None


@dataclass
class EventTrackerConfig:
    """이벤트 트래커 설정."""
    stability_threshold: float = 2.0  # 무게 안정화 대기 시간 (초)
    event_timeout: float = 30.0  # 이벤트 타임아웃 (초)
    camera_off_delay: float = 10.0  # 카메라 off 지연 (초)
    settling_time: float = 2.0  # 이벤트 안정화 시간 (초)
    return_window: float = 30.0  # 반납 감지 시간 윈도우 (초)
    match_tolerance: float = 0.15  # 반납 무게 매칭 허용 오차 (비율)
    max_history: int = 100  # 최대 히스토리 크기


class EventTracker:
    """
    이벤트 트래커.

    Zone별 이벤트 상태를 추적합니다.
    """

    def __init__(
        self,
        config: Optional[EventTrackerConfig] = None,
        settling_time: float = 2.0,
        return_window: float = 30.0,
        match_tolerance: float = 0.15,
        max_history: int = 100,
    ):
        """
        초기화.

        Args:
            config: 트래커 설정 (우선 사용)
            settling_time: 이벤트 안정화 시간 (초) - config 없을 때 사용
            return_window: 반납 감지 시간 윈도우 (초)
            match_tolerance: 반납 무게 매칭 허용 오차 (비율)
            max_history: 최대 히스토리 크기
        """
        if config:
            self.config = config
            self.settling_time = config.settling_time
            self.return_window = config.return_window
            self.match_tolerance = config.match_tolerance
            self.max_history = config.max_history
        else:
            self.config = EventTrackerConfig(
                settling_time=settling_time,
                return_window=return_window,
                match_tolerance=match_tolerance,
                max_history=max_history,
            )
            self.settling_time = settling_time
            self.return_window = return_window
            self.match_tolerance = match_tolerance
            self.max_history = max_history

        # Zone-based tracking (활성화된 zone만)
        self.zones: Dict[int, ZoneEvent] = {}
        for zone_id in get_enabled_zones():
            self.zones[zone_id] = ZoneEvent(zone_id=zone_id)

        # Event history (for advanced features)
        self.events: List[WeightEvent] = []

    # ========== Event History Methods (for advanced modules) ==========

    def add_event(
        self,
        zone_id: int,
        delta_weight: float,
        product_id: Optional[int] = None,
        product_name: Optional[str] = None,
        count: Optional[int] = None,
    ) -> WeightEvent:
        """
        새 이벤트 추가.

        Args:
            zone_id: Zone ID
            delta_weight: 무게 변화량
            product_id: 상품 ID (옵션)
            product_name: 상품 이름 (옵션)
            count: 개수 (옵션)

        Returns:
            생성된 WeightEvent
        """
        # 방향 결정
        if delta_weight < 0:
            direction = EventDirection.PICKUP
        else:
            direction = EventDirection.RETURN

        event = WeightEvent(
            timestamp=time.time(),
            zone_id=zone_id,
            delta_weight=delta_weight,
            direction=direction,
            product_id=product_id,
            product_name=product_name,
            count=count,
        )

        self.events.append(event)

        # 히스토리 크기 제한
        if len(self.events) > self.max_history:
            self.events = self.events[-self.max_history:]

        logger.debug(
            f"Event added: zone={zone_id}, delta={delta_weight:.1f}g, "
            f"direction={direction.value}"
        )

        return event

    def get_pending_events(self) -> List[WeightEvent]:
        """
        안정화되지 않은 이벤트 목록.

        Returns:
            미안정화 WeightEvent 리스트
        """
        current_time = time.time()
        pending = []

        for event in self.events:
            if not event.settled:
                if current_time - event.timestamp < self.settling_time:
                    pending.append(event)
                else:
                    # 시간 초과 시 자동 안정화
                    event.settled = True

        return pending

    def mark_settled(self, event_id: str) -> bool:
        """
        이벤트를 안정화됨으로 표시.

        Args:
            event_id: 이벤트 ID

        Returns:
            성공 여부
        """
        for event in self.events:
            if event.event_id == event_id:
                event.settled = True
                logger.debug(f"Event {event_id} marked as settled")
                return True
        return False

    def detect_return(
        self,
        new_event: WeightEvent,
    ) -> ReturnResult:
        """
        반납 이벤트 감지.

        양수 무게 변화(new_event)가 최근 픽업 이벤트와 매칭되는지 확인.

        Args:
            new_event: 새 이벤트 (양수 무게 변화)

        Returns:
            ReturnResult
        """
        # 양수 무게 변화만 반납 가능
        if new_event.delta_weight <= 0:
            return ReturnResult(is_return=False)

        current_time = time.time()
        best_match: Optional[WeightEvent] = None
        best_score = 0.0

        # 최근 픽업 이벤트 중 매칭 찾기
        for event in reversed(self.events):
            # 시간 윈도우 체크
            if current_time - event.timestamp > self.return_window:
                continue

            # 픽업 이벤트만 대상
            if not event.is_pickup:
                continue

            # 이미 매칭된 이벤트 제외
            if event.matched_event_id:
                continue

            # 같은 Zone만 대상 (또는 Cross-Zone 허용 시 별도 처리)
            if event.zone_id != new_event.zone_id:
                continue

            # 무게 매칭 점수 계산
            original_weight = abs(event.delta_weight)
            return_weight = new_event.delta_weight
            weight_diff = abs(original_weight - return_weight)
            max_diff = original_weight * self.match_tolerance

            if weight_diff <= max_diff:
                score = 1.0 - (weight_diff / original_weight) if original_weight > 0 else 0
                if score > best_score:
                    best_score = score
                    best_match = event

        if best_match:
            # 매칭 성공
            best_match.matched_event_id = new_event.event_id
            new_event.matched_event_id = best_match.event_id
            new_event.direction = EventDirection.RETURN

            logger.info(
                f"Return detected: original={best_match.abs_weight:.1f}g, "
                f"return={new_event.delta_weight:.1f}g, score={best_score:.3f}"
            )

            return ReturnResult(
                is_return=True,
                original_event=best_match,
                return_event=new_event,
                weight_match_score=best_score,
                should_cancel=True,  # 결제 취소 권장
            )

        return ReturnResult(is_return=False)

    def get_recent_pickups(
        self,
        zone_id: Optional[int] = None,
        time_window: Optional[float] = None,
    ) -> List[WeightEvent]:
        """
        최근 픽업 이벤트 목록.

        Args:
            zone_id: Zone ID (None이면 전체)
            time_window: 시간 윈도우 (None이면 return_window 사용)

        Returns:
            픽업 WeightEvent 리스트
        """
        window = time_window or self.return_window
        current_time = time.time()
        pickups = []

        for event in reversed(self.events):
            if current_time - event.timestamp > window:
                break

            if event.is_pickup:
                if zone_id is None or event.zone_id == zone_id:
                    pickups.append(event)

        return pickups

    def get_zone_history(
        self,
        zone_id: int,
        limit: int = 10,
    ) -> List[WeightEvent]:
        """
        특정 Zone의 이벤트 히스토리.

        Args:
            zone_id: Zone ID
            limit: 최대 개수

        Returns:
            WeightEvent 리스트 (최신순)
        """
        zone_events = [e for e in self.events if e.zone_id == zone_id]
        return list(reversed(zone_events[-limit:]))

    def clear_old_events(self, max_age: float = 300.0) -> int:
        """
        오래된 이벤트 정리.

        Args:
            max_age: 최대 보관 시간 (초)

        Returns:
            삭제된 이벤트 수
        """
        current_time = time.time()
        original_count = len(self.events)

        self.events = [
            e for e in self.events
            if current_time - e.timestamp <= max_age
        ]

        removed = original_count - len(self.events)
        if removed > 0:
            logger.debug(f"Cleared {removed} old events")

        return removed

    # ========== Zone-based Methods (original functionality) ==========

    def on_weight_change(self, zone_id: int, delta_weight: float) -> ZoneEvent:
        """
        무게 변화 감지 시 호출.

        Args:
            zone_id: Zone ID
            delta_weight: 무게 변화량

        Returns:
            업데이트된 ZoneEvent
        """
        now = time.time()
        zone = self.zones.get(zone_id)

        if not zone:
            zone = ZoneEvent(zone_id=zone_id)
            self.zones[zone_id] = zone

        if zone.state == EventState.IDLE:
            # 새 이벤트 시작
            zone.state = EventState.ACTIVE
            zone.start_time = now
            zone.delta_weight = delta_weight
            zone.last_update_time = now
            zone.stable_since = None
            logger.info(f"Zone {zone_id} event started: delta={delta_weight:.1f}g")
        else:
            # 기존 이벤트 업데이트
            zone.delta_weight += delta_weight
            zone.last_update_time = now
            zone.stable_since = None  # 변화가 있으면 안정화 리셋
            logger.debug(f"Zone {zone_id} event updated: total_delta={zone.delta_weight:.1f}g")

        return zone

    def on_weight_stable(self, zone_id: int) -> ZoneEvent:
        """
        무게 안정화 감지 시 호출.

        Args:
            zone_id: Zone ID

        Returns:
            업데이트된 ZoneEvent
        """
        now = time.time()
        zone = self.zones.get(zone_id)

        if not zone or zone.state == EventState.IDLE:
            return zone

        if zone.stable_since is None:
            zone.stable_since = now
            logger.debug(f"Zone {zone_id} weight stabilizing...")

        # 안정화 시간 경과 체크
        if now - zone.stable_since >= self.config.stability_threshold:
            zone.state = EventState.PROCESSING
            logger.info(f"Zone {zone_id} weight stable, ready for processing")

        return zone

    def on_processing_complete(
        self,
        zone_id: int,
        result: dict,
    ) -> ZoneEvent:
        """
        처리 완료 시 호출.

        Args:
            zone_id: Zone ID
            result: 판단 결과

        Returns:
            업데이트된 ZoneEvent
        """
        zone = self.zones.get(zone_id)
        if zone:
            zone.state = EventState.COMPLETED
            zone.judgment_result = result
            logger.info(f"Zone {zone_id} processing completed")
        return zone

    def reset_zone(self, zone_id: int) -> ZoneEvent:
        """
        Zone 상태 리셋.

        Args:
            zone_id: Zone ID

        Returns:
            리셋된 ZoneEvent
        """
        zone = ZoneEvent(zone_id=zone_id)
        self.zones[zone_id] = zone
        logger.debug(f"Zone {zone_id} reset to IDLE")
        return zone

    def check_timeouts(self) -> List[int]:
        """
        타임아웃된 Zone 체크.

        Returns:
            타임아웃된 Zone ID 리스트
        """
        now = time.time()
        timeout_zones = []

        for zone_id, zone in self.zones.items():
            if zone.state in [EventState.ACTIVE, EventState.PROCESSING]:
                if zone.start_time and (now - zone.start_time) > self.config.event_timeout:
                    zone.state = EventState.TIMEOUT
                    timeout_zones.append(zone_id)
                    logger.warning(f"Zone {zone_id} event timeout")

        return timeout_zones

    def get_active_zones(self) -> List[ZoneEvent]:
        """
        활성 상태인 Zone 리스트 반환.

        Returns:
            활성 ZoneEvent 리스트
        """
        return [
            zone for zone in self.zones.values()
            if zone.state in [EventState.ACTIVE, EventState.PROCESSING]
        ]

    def get_zone_state(self, zone_id: int) -> EventState:
        """
        Zone 상태 조회.

        Args:
            zone_id: Zone ID

        Returns:
            EventState
        """
        zone = self.zones.get(zone_id)
        return zone.state if zone else EventState.IDLE

    def to_dict(self) -> dict:
        """상태 딕셔너리 변환."""
        return {
            "event_count": len(self.events),
            "pending_count": len(self.get_pending_events()),
            "settling_time": self.settling_time,
            "return_window": self.return_window,
            "recent_events": [e.to_dict() for e in self.events[-5:]],
            "zones": {
                zone_id: {
                    "state": zone.state.value,
                    "delta_weight": round(zone.delta_weight, 1) if zone.delta_weight else 0,
                }
                for zone_id, zone in self.zones.items()
            },
        }
