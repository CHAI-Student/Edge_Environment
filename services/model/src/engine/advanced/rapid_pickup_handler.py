"""
Rapid Pickup Handler.

빠른 연속 취출 처리 (시나리오 8).

핵심 기능:
1. 이벤트 버퍼링 (빠른 연속 취출 수집)
2. 무게 안정화 감지 (변동 < threshold)
3. 버퍼된 이벤트 일괄 처리
4. 2~10개 상품 연속 취출 지원

사용 예시:
    handler = RapidPickupHandler(buffer_window=3.0)

    # 연속 취출 중
    handler.add_event(delta=-365.0, timestamp=t1)
    handler.add_event(delta=-520.0, timestamp=t2)

    # 안정화 후 처리
    if handler.is_settled():
        events = handler.flush_buffer()
        total_delta = sum(e.delta for e in events)
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class BufferedWeightEvent:
    """
    버퍼링된 무게 이벤트.

    Attributes:
        timestamp: 이벤트 시각
        delta_weight: 무게 변화량
        cumulative_delta: 누적 변화량
        zone_id: Zone ID
    """
    timestamp: float
    delta_weight: float
    cumulative_delta: float = 0.0
    zone_id: int = 0

    @property
    def age(self) -> float:
        """이벤트 발생 후 경과 시간."""
        return time.time() - self.timestamp

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "timestamp": self.timestamp,
            "delta_weight": round(self.delta_weight, 1),
            "cumulative_delta": round(self.cumulative_delta, 1),
            "zone_id": self.zone_id,
            "age": round(self.age, 2),
        }


@dataclass
class RapidPickupResult:
    """
    연속 취출 처리 결과.

    Attributes:
        events: 버퍼된 이벤트 리스트
        total_delta: 총 무게 변화량
        event_count: 이벤트 수
        duration: 취출 소요 시간 (초)
        is_complete: 처리 완료 여부
    """
    events: List[BufferedWeightEvent] = field(default_factory=list)
    total_delta: float = 0.0
    event_count: int = 0
    duration: float = 0.0
    is_complete: bool = False

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "event_count": self.event_count,
            "total_delta": round(self.total_delta, 1),
            "duration": round(self.duration, 2),
            "is_complete": self.is_complete,
            "events": [e.to_dict() for e in self.events],
        }


class RapidPickupHandler:
    """
    빠른 연속 취출 핸들러.

    빠른 연속 취출을 버퍼링하고 안정화 후 일괄 처리합니다.

    Attributes:
        buffer_window: 버퍼 윈도우 시간 (초)
        settling_threshold: 안정화 임계값 (g)
        settling_time: 안정화 대기 시간 (초)
        max_events: 최대 버퍼 이벤트 수
    """

    def __init__(
        self,
        buffer_window: float = 3.0,
        settling_threshold: float = 5.0,
        settling_time: float = 1.0,
        max_events: int = 15,
    ):
        """
        핸들러 초기화.

        Args:
            buffer_window: 버퍼 윈도우 시간 (초)
            settling_threshold: 안정화 임계값 (g)
            settling_time: 안정화 대기 시간 (초)
            max_events: 최대 버퍼 이벤트 수
        """
        self.buffer_window = buffer_window
        self.settling_threshold = settling_threshold
        self.settling_time = settling_time
        self.max_events = max_events

        self.event_buffer: List[BufferedWeightEvent] = []
        self.last_weight_change: float = 0.0
        self.last_change_time: float = 0.0
        self.buffer_start_time: Optional[float] = None
        self._cumulative_delta: float = 0.0

    def add_event(
        self,
        delta_weight: float,
        timestamp: Optional[float] = None,
        zone_id: int = 0,
    ) -> bool:
        """
        이벤트 추가.

        Args:
            delta_weight: 무게 변화량
            timestamp: 이벤트 시각 (None이면 현재 시간)
            zone_id: Zone ID

        Returns:
            버퍼에 추가됨 여부
        """
        if timestamp is None:
            timestamp = time.time()

        # 버퍼 시작 시간 기록
        if self.buffer_start_time is None:
            self.buffer_start_time = timestamp

        # 누적 변화량 업데이트
        self._cumulative_delta += delta_weight

        event = BufferedWeightEvent(
            timestamp=timestamp,
            delta_weight=delta_weight,
            cumulative_delta=self._cumulative_delta,
            zone_id=zone_id,
        )

        self.event_buffer.append(event)
        self.last_weight_change = abs(delta_weight)
        self.last_change_time = timestamp

        # 버퍼 크기 제한
        if len(self.event_buffer) > self.max_events:
            self.event_buffer = self.event_buffer[-self.max_events:]

        logger.debug(
            f"Event buffered: delta={delta_weight:.1f}g, "
            f"cumulative={self._cumulative_delta:.1f}g, "
            f"buffer_size={len(self.event_buffer)}"
        )

        return True

    def is_settled(self, current_time: Optional[float] = None) -> bool:
        """
        무게 안정화 여부.

        마지막 변화 이후 settling_time이 경과하고
        최근 변화가 settling_threshold 미만이면 안정화로 판단.

        Args:
            current_time: 현재 시각 (None이면 자동)

        Returns:
            안정화 여부
        """
        if not self.event_buffer:
            return True

        if current_time is None:
            current_time = time.time()

        # 마지막 변화 이후 경과 시간
        time_since_change = current_time - self.last_change_time

        return time_since_change >= self.settling_time

    def is_active(self, current_time: Optional[float] = None) -> bool:
        """
        버퍼가 활성 상태인지 (연속 취출 중).

        Args:
            current_time: 현재 시각

        Returns:
            활성 여부
        """
        if not self.event_buffer:
            return False

        if current_time is None:
            current_time = time.time()

        # 버퍼 윈도우 내에 있고 안정화되지 않음
        if self.buffer_start_time is None:
            return False

        buffer_age = current_time - self.buffer_start_time
        return buffer_age <= self.buffer_window and not self.is_settled(current_time)

    def flush_buffer(self) -> RapidPickupResult:
        """
        버퍼 비우기 및 결과 반환.

        Returns:
            RapidPickupResult
        """
        if not self.event_buffer:
            return RapidPickupResult(is_complete=True)

        # 결과 생성
        events = list(self.event_buffer)
        total_delta = self._cumulative_delta

        duration = 0.0
        if len(events) >= 2:
            duration = events[-1].timestamp - events[0].timestamp

        result = RapidPickupResult(
            events=events,
            total_delta=total_delta,
            event_count=len(events),
            duration=duration,
            is_complete=True,
        )

        logger.info(
            f"Buffer flushed: {len(events)} events, "
            f"total_delta={total_delta:.1f}g, duration={duration:.2f}s"
        )

        # 버퍼 초기화
        self.clear_buffer()

        return result

    def clear_buffer(self):
        """버퍼 초기화."""
        self.event_buffer.clear()
        self._cumulative_delta = 0.0
        self.buffer_start_time = None
        self.last_weight_change = 0.0
        self.last_change_time = 0.0

    def get_cumulative_delta(self) -> float:
        """현재 누적 무게 변화량."""
        return self._cumulative_delta

    def get_buffer_duration(self, current_time: Optional[float] = None) -> float:
        """
        버퍼 경과 시간.

        Args:
            current_time: 현재 시각

        Returns:
            경과 시간 (초)
        """
        if self.buffer_start_time is None:
            return 0.0

        if current_time is None:
            current_time = time.time()

        return current_time - self.buffer_start_time

    def get_event_rate(self) -> float:
        """
        이벤트 발생 속도 (events/sec).

        Returns:
            초당 이벤트 수
        """
        duration = self.get_buffer_duration()
        if duration <= 0 or not self.event_buffer:
            return 0.0

        return len(self.event_buffer) / duration

    def should_process(self, current_time: Optional[float] = None) -> bool:
        """
        처리 필요 여부 (안정화 && 버퍼 비어있지 않음).

        Args:
            current_time: 현재 시각

        Returns:
            처리 필요 여부
        """
        return bool(self.event_buffer) and self.is_settled(current_time)

    def peek_buffer(self) -> RapidPickupResult:
        """
        버퍼 미리보기 (비우지 않음).

        Returns:
            현재 버퍼 상태의 RapidPickupResult
        """
        if not self.event_buffer:
            return RapidPickupResult()

        duration = 0.0
        if len(self.event_buffer) >= 2:
            duration = self.event_buffer[-1].timestamp - self.event_buffer[0].timestamp

        return RapidPickupResult(
            events=list(self.event_buffer),
            total_delta=self._cumulative_delta,
            event_count=len(self.event_buffer),
            duration=duration,
            is_complete=False,
        )

    def to_dict(self) -> dict:
        """상태 딕셔너리 변환."""
        return {
            "buffer_window": self.buffer_window,
            "settling_threshold": self.settling_threshold,
            "settling_time": self.settling_time,
            "event_count": len(self.event_buffer),
            "cumulative_delta": round(self._cumulative_delta, 1),
            "is_settled": self.is_settled(),
            "is_active": self.is_active(),
            "buffer_duration": round(self.get_buffer_duration(), 2),
            "event_rate": round(self.get_event_rate(), 2),
        }
