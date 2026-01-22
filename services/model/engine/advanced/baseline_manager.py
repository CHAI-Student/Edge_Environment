"""
Baseline Manager.

장시간 도어 오픈 시 Baseline 드리프트 보정 (시나리오 7).

핵심 기능:
1. 시간 경과에 따른 드리프트 추정
2. 보정된 무게 변화량 계산
3. Baseline 자동 갱신 스케줄링
4. 장시간 오픈 시나리오 지원 (1~5분)

사용 예시:
    manager = BaselineManager(drift_rate=0.5)
    manager.set_baseline(zone_id=0, weight=1000.0)

    # 3분 후
    corrected = manager.get_corrected_delta(
        zone_id=0,
        current_weight=990.0,
        elapsed_time=180.0
    )
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class ZoneBaseline:
    """
    Zone별 Baseline 정보.

    Attributes:
        zone_id: Zone ID
        baseline: 기준 무게 (g)
        set_time: 설정 시각
        last_refresh: 마지막 갱신 시각
        drift_accumulated: 누적 드리프트 (g)
        sample_count: 샘플 수 (드리프트 학습용)
    """
    zone_id: int
    baseline: float = 0.0
    set_time: float = field(default_factory=time.time)
    last_refresh: float = field(default_factory=time.time)
    drift_accumulated: float = 0.0
    sample_count: int = 0

    @property
    def elapsed_time(self) -> float:
        """Baseline 설정 후 경과 시간 (초)."""
        return time.time() - self.set_time

    @property
    def time_since_refresh(self) -> float:
        """마지막 갱신 후 경과 시간 (초)."""
        return time.time() - self.last_refresh


class BaselineManager:
    """
    Baseline 드리프트 관리자.

    장시간 도어 오픈 시 발생하는 센서 드리프트를 보정합니다.

    Attributes:
        drift_rate: 예상 드리프트 속도 (g/min)
        refresh_interval: 자동 갱신 간격 (초)
        max_drift: 최대 허용 드리프트 (g)
        zone_count: Zone 수
    """

    def __init__(
        self,
        drift_rate: float = 0.5,
        refresh_interval: float = 60.0,
        max_drift: float = 10.0,
        zone_count: int = 5,
    ):
        """
        관리자 초기화.

        Args:
            drift_rate: 예상 드리프트 속도 (g/min)
            refresh_interval: 자동 갱신 간격 (초)
            max_drift: 최대 허용 드리프트 (g)
            zone_count: Zone 수
        """
        self.drift_rate = drift_rate
        self.refresh_interval = refresh_interval
        self.max_drift = max_drift
        self.zone_count = zone_count

        self.baselines: Dict[int, ZoneBaseline] = {}
        self._learned_drift_rates: Dict[int, List[float]] = {}

    def set_baseline(
        self,
        zone_id: int,
        weight: float,
    ):
        """
        Zone baseline 설정.

        Args:
            zone_id: Zone ID
            weight: 기준 무게 (g)
        """
        current_time = time.time()

        self.baselines[zone_id] = ZoneBaseline(
            zone_id=zone_id,
            baseline=weight,
            set_time=current_time,
            last_refresh=current_time,
        )

        logger.info(f"Zone {zone_id} baseline set to {weight:.1f}g")

    def set_baselines_from_loadcell(
        self,
        loadcell_weights: List[float],
    ):
        """
        10채널 로드셀 데이터로 전체 baseline 설정.

        Args:
            loadcell_weights: 10채널 무게 리스트
        """
        for zone_id in range(self.zone_count):
            start_idx = zone_id * 2
            zone_weight = sum(loadcell_weights[start_idx:start_idx + 2])
            self.set_baseline(zone_id, zone_weight)

    def get_corrected_delta(
        self,
        zone_id: int,
        current_weight: float,
        elapsed_time: Optional[float] = None,
    ) -> float:
        """
        드리프트 보정된 무게 변화량 계산.

        Args:
            zone_id: Zone ID
            current_weight: 현재 무게 (g)
            elapsed_time: 경과 시간 (초, None이면 자동 계산)

        Returns:
            보정된 무게 변화량 (g)
        """
        baseline_info = self.baselines.get(zone_id)

        if baseline_info is None:
            logger.warning(f"No baseline for zone {zone_id}, using current weight")
            return 0.0

        # 경과 시간 계산
        if elapsed_time is None:
            elapsed_time = baseline_info.elapsed_time

        # 드리프트 추정
        drift_correction = self._estimate_drift(zone_id, elapsed_time)

        # 보정된 baseline
        corrected_baseline = baseline_info.baseline + drift_correction

        # 무게 변화량
        raw_delta = current_weight - baseline_info.baseline
        corrected_delta = current_weight - corrected_baseline

        logger.debug(
            f"Zone {zone_id}: raw_delta={raw_delta:.1f}g, "
            f"drift={drift_correction:.2f}g, corrected={corrected_delta:.1f}g"
        )

        return corrected_delta

    def _estimate_drift(
        self,
        zone_id: int,
        elapsed_time: float,
    ) -> float:
        """
        드리프트 추정.

        Args:
            zone_id: Zone ID
            elapsed_time: 경과 시간 (초)

        Returns:
            추정 드리프트 (g)
        """
        # 학습된 드리프트 율 사용
        if zone_id in self._learned_drift_rates and self._learned_drift_rates[zone_id]:
            learned_rate = sum(self._learned_drift_rates[zone_id]) / len(self._learned_drift_rates[zone_id])
            drift = learned_rate * (elapsed_time / 60.0)
        else:
            # 기본 드리프트 율 사용
            drift = self.drift_rate * (elapsed_time / 60.0)

        # 최대 드리프트 제한
        drift = max(-self.max_drift, min(drift, self.max_drift))

        return drift

    def should_refresh(
        self,
        zone_id: int,
        current_time: Optional[float] = None,
    ) -> bool:
        """
        Baseline 갱신 필요 여부.

        Args:
            zone_id: Zone ID
            current_time: 현재 시각 (None이면 자동)

        Returns:
            갱신 필요 여부
        """
        baseline_info = self.baselines.get(zone_id)
        if baseline_info is None:
            return True

        if current_time is None:
            current_time = time.time()

        return (current_time - baseline_info.last_refresh) >= self.refresh_interval

    def refresh_baseline(
        self,
        zone_id: int,
        current_weight: float,
    ):
        """
        Baseline 갱신 (드리프트 학습 포함).

        Args:
            zone_id: Zone ID
            current_weight: 현재 무게 (g)
        """
        baseline_info = self.baselines.get(zone_id)

        if baseline_info is not None:
            # 드리프트 학습
            elapsed = baseline_info.time_since_refresh
            if elapsed > 0:
                observed_drift = current_weight - baseline_info.baseline
                drift_rate = (observed_drift / elapsed) * 60.0  # g/min

                if zone_id not in self._learned_drift_rates:
                    self._learned_drift_rates[zone_id] = []

                self._learned_drift_rates[zone_id].append(drift_rate)

                # 최근 10개만 유지
                if len(self._learned_drift_rates[zone_id]) > 10:
                    self._learned_drift_rates[zone_id] = self._learned_drift_rates[zone_id][-10:]

        # Baseline 갱신
        self.set_baseline(zone_id, current_weight)

    def get_long_open_correction(
        self,
        zone_id: int,
        door_open_duration: float,
        current_weight: float,
    ) -> float:
        """
        장시간 도어 오픈 시 보정된 무게 변화량.

        시나리오 7 전용: 1~5분 도어 오픈 후 취출.

        Args:
            zone_id: Zone ID
            door_open_duration: 도어 오픈 시간 (초)
            current_weight: 현재 무게 (g)

        Returns:
            보정된 무게 변화량 (g)
        """
        # 긴 시간 동안 드리프트 보정
        return self.get_corrected_delta(
            zone_id=zone_id,
            current_weight=current_weight,
            elapsed_time=door_open_duration,
        )

    def get_all_baselines(self) -> Dict[int, float]:
        """
        모든 Zone의 baseline 조회.

        Returns:
            {zone_id: baseline} 딕셔너리
        """
        return {
            zone_id: info.baseline
            for zone_id, info in self.baselines.items()
        }

    def get_zone_status(self, zone_id: int) -> Optional[dict]:
        """
        Zone 상태 조회.

        Args:
            zone_id: Zone ID

        Returns:
            상태 딕셔너리 또는 None
        """
        info = self.baselines.get(zone_id)
        if info is None:
            return None

        learned_rate = None
        if zone_id in self._learned_drift_rates and self._learned_drift_rates[zone_id]:
            learned_rate = sum(self._learned_drift_rates[zone_id]) / len(self._learned_drift_rates[zone_id])

        return {
            "zone_id": zone_id,
            "baseline": round(info.baseline, 1),
            "elapsed_time": round(info.elapsed_time, 1),
            "time_since_refresh": round(info.time_since_refresh, 1),
            "should_refresh": self.should_refresh(zone_id),
            "estimated_drift": round(self._estimate_drift(zone_id, info.elapsed_time), 2),
            "learned_drift_rate": round(learned_rate, 3) if learned_rate else None,
        }

    def to_dict(self) -> dict:
        """상태 딕셔너리 변환."""
        return {
            "drift_rate": self.drift_rate,
            "refresh_interval": self.refresh_interval,
            "max_drift": self.max_drift,
            "zones": {
                zone_id: self.get_zone_status(zone_id)
                for zone_id in self.baselines.keys()
            },
        }
