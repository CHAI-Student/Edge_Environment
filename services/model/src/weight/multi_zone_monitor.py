"""
Multi-Zone Weight Monitor.

5개 Zone 동시 무게 변화 모니터링.

핵심 기능:
1. Zone별 baseline 관리
2. 동시 다발적 무게 변화 감지
3. Cross-Zone 이동 감지 (A Zone -X, B Zone +X)
4. Baseline 갱신 및 드리프트 추적

Zone 구성:
- Zone 0: LoadCell 1, 2
- Zone 1: LoadCell 3, 4
- Zone 2: LoadCell 5, 6
- Zone 3: LoadCell 7, 8
- Zone 4: LoadCell 9, 10

사용 예시:
    monitor = MultiZoneWeightMonitor()
    event = monitor.update(zone_id=0, weight=1230.5)
    cross_move = monitor.detect_cross_zone_movement()
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import time
import logging

from ..engine.event_tracker import WeightEvent, EventDirection

logger = logging.getLogger(__name__)


@dataclass
class ZoneWeightState:
    """
    Zone 무게 상태.

    Attributes:
        zone_id: Zone ID (0-4)
        baseline: 기준 무게 (g)
        current_weight: 현재 무게 (g)
        last_update: 마지막 업데이트 시각
        stable: 안정화 여부
        pending_delta: 미처리 무게 변화량
    """
    zone_id: int
    baseline: float = 0.0
    current_weight: float = 0.0
    last_update: float = 0.0
    stable: bool = True
    pending_delta: float = 0.0

    @property
    def delta(self) -> float:
        """현재 무게 변화량."""
        return self.current_weight - self.baseline

    @property
    def abs_delta(self) -> float:
        """절대 무게 변화량."""
        return abs(self.delta)


@dataclass
class CrossZoneMovement:
    """
    Cross-Zone 이동 결과.

    Attributes:
        detected: 이동 감지 여부
        source_zone: 출발 Zone ID
        target_zone: 도착 Zone ID
        weight: 이동 무게 (g)
        match_score: 무게 매칭 점수
    """
    detected: bool
    source_zone: int = -1
    target_zone: int = -1
    weight: float = 0.0
    match_score: float = 0.0

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "detected": self.detected,
            "source_zone": self.source_zone,
            "target_zone": self.target_zone,
            "weight": round(self.weight, 1),
            "match_score": round(self.match_score, 3),
        }


class MultiZoneWeightMonitor:
    """
    다중 Zone 무게 모니터.

    5개 Zone의 무게를 동시에 추적하고 이벤트를 감지합니다.

    Attributes:
        zone_count: Zone 수 (기본값 5)
        change_threshold: 변화 감지 임계값 (g)
        settling_time: 안정화 시간 (초)
        cross_zone_tolerance: Cross-Zone 매칭 허용 오차 (비율)
    """

    def __init__(
        self,
        zone_count: int = 5,
        change_threshold: float = 5.0,
        settling_time: float = 2.0,
        cross_zone_tolerance: float = 0.10,
    ):
        """
        모니터 초기화.

        Args:
            zone_count: Zone 수
            change_threshold: 변화 감지 임계값 (g)
            settling_time: 안정화 시간 (초)
            cross_zone_tolerance: Cross-Zone 매칭 허용 오차
        """
        self.zone_count = zone_count
        self.change_threshold = change_threshold
        self.settling_time = settling_time
        self.cross_zone_tolerance = cross_zone_tolerance

        # Zone별 상태 초기화
        self.zones: List[ZoneWeightState] = [
            ZoneWeightState(zone_id=i)
            for i in range(zone_count)
        ]

        # 이벤트 버퍼 (안정화 전 이벤트)
        self.pending_events: Dict[int, WeightEvent] = {}

    def update(
        self,
        zone_id: int,
        weight: float,
    ) -> Optional[WeightEvent]:
        """
        Zone 무게 업데이트.

        Args:
            zone_id: Zone ID
            weight: 현재 무게 (g)

        Returns:
            감지된 WeightEvent 또는 None
        """
        if zone_id < 0 or zone_id >= self.zone_count:
            logger.warning(f"Invalid zone_id: {zone_id}")
            return None

        zone = self.zones[zone_id]
        current_time = time.time()

        # 이전 무게 저장
        prev_weight = zone.current_weight
        zone.current_weight = weight
        zone.last_update = current_time

        # 무게 변화 계산
        delta = weight - zone.baseline

        # 변화 감지
        if abs(delta) >= self.change_threshold:
            # 이전에 안정 상태였으면 새 이벤트 시작
            if zone.stable:
                zone.stable = False
                zone.pending_delta = delta

                direction = EventDirection.PICKUP if delta < 0 else EventDirection.RETURN

                event = WeightEvent(
                    timestamp=current_time,
                    zone_id=zone_id,
                    delta_weight=delta,
                    direction=direction,
                )

                self.pending_events[zone_id] = event

                logger.debug(
                    f"Zone {zone_id} change detected: delta={delta:.1f}g, "
                    f"direction={direction.value}"
                )

                return event
            else:
                # 진행 중인 이벤트 업데이트
                zone.pending_delta = delta
                if zone_id in self.pending_events:
                    self.pending_events[zone_id].delta_weight = delta

        else:
            # 변화가 임계값 미만이면 안정화
            if not zone.stable:
                zone.stable = True
                zone.pending_delta = 0.0

                if zone_id in self.pending_events:
                    event = self.pending_events.pop(zone_id)
                    event.settled = True
                    logger.debug(f"Zone {zone_id} settled")

        return None

    def update_from_loadcell(
        self,
        loadcell_weights: List[float],
    ) -> List[Optional[WeightEvent]]:
        """
        10채널 로드셀 데이터로 업데이트.

        Args:
            loadcell_weights: 10채널 로드셀 무게 리스트

        Returns:
            Zone별 WeightEvent 리스트
        """
        events = []

        for zone_id in range(self.zone_count):
            start_idx = zone_id * 2
            zone_weight = sum(loadcell_weights[start_idx:start_idx + 2])
            event = self.update(zone_id, zone_weight)
            events.append(event)

        return events

    def set_baseline(
        self,
        zone_id: int,
        baseline: Optional[float] = None,
    ):
        """
        Zone baseline 설정.

        Args:
            zone_id: Zone ID
            baseline: 기준 무게 (None이면 현재 무게 사용)
        """
        if zone_id < 0 or zone_id >= self.zone_count:
            return

        zone = self.zones[zone_id]

        if baseline is not None:
            zone.baseline = baseline
        else:
            zone.baseline = zone.current_weight

        logger.info(f"Zone {zone_id} baseline set to {zone.baseline:.1f}g")

    def set_baselines_from_loadcell(
        self,
        baseline_weights: List[float],
    ):
        """
        10채널 로드셀 데이터로 baseline 설정.

        Args:
            baseline_weights: 10채널 기준 무게 리스트
        """
        for zone_id in range(self.zone_count):
            start_idx = zone_id * 2
            zone_baseline = sum(baseline_weights[start_idx:start_idx + 2])
            self.set_baseline(zone_id, zone_baseline)

    def refresh_baseline(self, zone_id: int):
        """
        현재 무게를 baseline으로 갱신.

        Args:
            zone_id: Zone ID
        """
        self.set_baseline(zone_id, None)

    def refresh_all_baselines(self):
        """모든 Zone의 baseline 갱신."""
        for zone_id in range(self.zone_count):
            self.refresh_baseline(zone_id)

    def get_active_zones(self) -> List[int]:
        """
        현재 무게 변화가 감지된 Zone 목록.

        Returns:
            Zone ID 리스트
        """
        active = []
        for zone in self.zones:
            if zone.abs_delta >= self.change_threshold:
                active.append(zone.zone_id)
        return active

    def get_zone_deltas(self) -> List[Tuple[int, float]]:
        """
        모든 Zone의 무게 변화량.

        Returns:
            [(zone_id, delta), ...] 리스트
        """
        return [
            (zone.zone_id, zone.delta)
            for zone in self.zones
        ]

    def detect_cross_zone_movement(self) -> CrossZoneMovement:
        """
        Cross-Zone 이동 감지.

        A Zone에서 무게 감소, B Zone에서 유사한 무게 증가 시
        상품 이동으로 판단.

        Returns:
            CrossZoneMovement
        """
        # 유의미한 변화가 있는 Zone 찾기
        negative_zones = []  # 무게 감소
        positive_zones = []  # 무게 증가

        for zone in self.zones:
            if zone.delta < -self.change_threshold:
                negative_zones.append(zone)
            elif zone.delta > self.change_threshold:
                positive_zones.append(zone)

        # 매칭 시도
        for neg_zone in negative_zones:
            for pos_zone in positive_zones:
                neg_weight = abs(neg_zone.delta)
                pos_weight = pos_zone.delta

                # 무게 차이 계산
                weight_diff = abs(neg_weight - pos_weight)
                tolerance = neg_weight * self.cross_zone_tolerance

                if weight_diff <= tolerance:
                    # 매칭 점수 계산
                    score = 1.0 - (weight_diff / neg_weight) if neg_weight > 0 else 0

                    logger.info(
                        f"Cross-zone movement detected: "
                        f"Zone {neg_zone.zone_id} -> Zone {pos_zone.zone_id}, "
                        f"weight={neg_weight:.1f}g, score={score:.3f}"
                    )

                    return CrossZoneMovement(
                        detected=True,
                        source_zone=neg_zone.zone_id,
                        target_zone=pos_zone.zone_id,
                        weight=neg_weight,
                        match_score=score,
                    )

        return CrossZoneMovement(detected=False)

    def get_pending_events(self) -> List[WeightEvent]:
        """
        안정화 대기 중인 이벤트 목록.

        Returns:
            WeightEvent 리스트
        """
        return list(self.pending_events.values())

    def get_zone_state(self, zone_id: int) -> Optional[ZoneWeightState]:
        """
        특정 Zone 상태 조회.

        Args:
            zone_id: Zone ID

        Returns:
            ZoneWeightState 또는 None
        """
        if 0 <= zone_id < self.zone_count:
            return self.zones[zone_id]
        return None

    def to_dict(self) -> dict:
        """상태 딕셔너리 변환."""
        return {
            "zone_count": self.zone_count,
            "change_threshold": self.change_threshold,
            "active_zones": self.get_active_zones(),
            "zones": [
                {
                    "zone_id": z.zone_id,
                    "baseline": round(z.baseline, 1),
                    "current": round(z.current_weight, 1),
                    "delta": round(z.delta, 1),
                    "stable": z.stable,
                }
                for z in self.zones
            ],
            "pending_events": len(self.pending_events),
        }
