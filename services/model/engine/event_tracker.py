"""
Event Tracker.

Zone별 이벤트 상태 추적 및 관리.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import time
import logging

logger = logging.getLogger(__name__)


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


class EventTracker:
    """
    이벤트 트래커.

    Zone별 이벤트 상태를 추적합니다.
    """

    def __init__(self, config: Optional[EventTrackerConfig] = None):
        """
        초기화.

        Args:
            config: 트래커 설정
        """
        self.config = config or EventTrackerConfig()
        self.zones: Dict[int, ZoneEvent] = {}

        # 5개 Zone 초기화
        for zone_id in range(5):
            self.zones[zone_id] = ZoneEvent(zone_id=zone_id)

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
