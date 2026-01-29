"""
Recording Data Processor.

IO Board에서 recording된 시리얼 데이터를 처리하여
무게 변화량(delta)을 계산합니다.

Recording 데이터 형식:
    [
        {"loadcells": ["+01234", "-00567", ...], "timestamp": "2024-01-01T12:00:00Z"},
        {"loadcells": ["+01235", "-00568", ...], "timestamp": "2024-01-01T12:00:01Z"},
        ...
    ]

사용 예시:
    processor = RecordingProcessor()
    weight_data = processor.process(recording_logs, zone_id=0)
    # weight_data.delta_weight, weight_data.before_weights, weight_data.after_weights
"""

import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class RecordingLog:
    """단일 recording 로그 항목."""
    loadcells: List[str]  # 10개 채널 로드셀 값 (예: ["+01234", "-00567", ...])
    timestamp: str  # ISO 8601 형식


@dataclass
class ProcessedWeightData:
    """처리된 무게 데이터."""
    before_weights: List[float] = field(default_factory=list)  # 초기 무게 (10채널)
    after_weights: List[float] = field(default_factory=list)  # 최종 무게 (10채널)
    delta_weight: float = 0.0  # Zone별 총 무게 변화량
    channels: List[int] = field(default_factory=list)  # 변화 감지된 채널
    zone_id: int = 0
    sample_count: int = 0  # 처리된 샘플 수
    baseline_sample_count: int = 0  # Baseline에 사용된 샘플 수
    current_sample_count: int = 0  # Current에 사용된 샘플 수


# Zone-Channel 매핑 (config.py와 동일)
ZONE_CHANNEL_MAP = {
    0: [0, 1],
    1: [2, 3],
    2: [4, 5],
    3: [6, 7],
    4: [8, 9],
}


class RecordingProcessor:
    """
    Recording 데이터 처리기.

    IO Board에서 recording된 시리얼 데이터를 분석하여
    무게 변화량을 계산합니다.

    Attributes:
        baseline_samples: Baseline 계산에 사용할 초기 샘플 수
        current_samples: Current 계산에 사용할 최종 샘플 수
        stability_threshold: 안정성 판단 임계값 (g)
        min_delta_threshold: 최소 변화 감지 임계값 (g)
    """

    def __init__(
        self,
        baseline_samples: int = 5,
        current_samples: int = 5,
        stability_threshold: float = 3.0,
        min_delta_threshold: float = 10.0,
    ):
        """
        처리기 초기화.

        Args:
            baseline_samples: Baseline 계산에 사용할 초기 샘플 수 (기본값 5)
            current_samples: Current 계산에 사용할 최종 샘플 수 (기본값 5)
            stability_threshold: 채널별 안정성 판단 임계값 (기본값 3g)
            min_delta_threshold: 최소 변화 감지 임계값 (기본값 10g)
        """
        self.baseline_samples = baseline_samples
        self.current_samples = current_samples
        self.stability_threshold = stability_threshold
        self.min_delta_threshold = min_delta_threshold

    def process(
        self,
        recording_logs: List[dict],
        zone_id: int = 0,
        zone_channels: Optional[List[int]] = None,
    ) -> ProcessedWeightData:
        """
        Recording 데이터 처리.

        Args:
            recording_logs: Recording 로그 리스트
                [{"loadcells": [...], "timestamp": "..."}, ...]
            zone_id: Zone ID (기본값 0)
            zone_channels: Zone에 해당하는 채널 리스트 (None이면 자동 결정)

        Returns:
            ProcessedWeightData: 처리된 무게 데이터
        """
        if not recording_logs:
            logger.warning("Empty recording logs provided")
            return ProcessedWeightData(zone_id=zone_id)

        # Zone 채널 결정
        if zone_channels is None:
            zone_channels = ZONE_CHANNEL_MAP.get(zone_id, [0, 1])

        # 로드셀 값 파싱
        parsed_logs = []
        for log in recording_logs:
            loadcells = log.get("loadcells", [])
            if len(loadcells) >= 10:
                parsed_values = [self._parse_loadcell_value(v) for v in loadcells[:10]]
                parsed_logs.append(parsed_values)

        if not parsed_logs:
            logger.warning("No valid loadcell data in recording logs")
            return ProcessedWeightData(zone_id=zone_id)

        sample_count = len(parsed_logs)

        # Baseline 계산 (초기 N개 샘플 평균)
        baseline_count = min(self.baseline_samples, sample_count // 2)
        baseline_samples = parsed_logs[:baseline_count] if baseline_count > 0 else [parsed_logs[0]]
        before_weights = self._calculate_average(baseline_samples)

        # Current 계산 (최종 N개 샘플 평균)
        current_count = min(self.current_samples, sample_count // 2)
        current_samples = parsed_logs[-current_count:] if current_count > 0 else [parsed_logs[-1]]
        after_weights = self._calculate_average(current_samples)

        # 채널별 Delta 계산
        channel_deltas = [
            after_weights[i] - before_weights[i]
            for i in range(10)
        ]

        # Zone별 Delta 합산
        zone_delta = sum(channel_deltas[ch] for ch in zone_channels if ch < 10)

        # 변화 감지된 채널 식별
        changed_channels = [
            ch for ch in zone_channels
            if ch < 10 and abs(channel_deltas[ch]) >= self.min_delta_threshold
        ]

        result = ProcessedWeightData(
            before_weights=before_weights,
            after_weights=after_weights,
            delta_weight=round(zone_delta, 1),
            channels=changed_channels,
            zone_id=zone_id,
            sample_count=sample_count,
            baseline_sample_count=len(baseline_samples),
            current_sample_count=len(current_samples),
        )

        logger.info(
            f"Recording processed: zone={zone_id}, samples={sample_count}, "
            f"baseline_samples={len(baseline_samples)}, current_samples={len(current_samples)}, "
            f"delta={zone_delta:.1f}g, changed_channels={changed_channels}"
        )

        return result

    def process_multi_zone(
        self,
        recording_logs: List[dict],
        active_zones: Optional[List[int]] = None,
    ) -> dict:
        """
        다중 Zone 동시 처리.

        Args:
            recording_logs: Recording 로그 리스트
            active_zones: 활성화할 Zone 리스트 (None이면 모든 Zone)

        Returns:
            Zone ID를 키로 하는 ProcessedWeightData 딕셔너리
        """
        if active_zones is None:
            active_zones = list(ZONE_CHANNEL_MAP.keys())

        results = {}
        for zone_id in active_zones:
            results[zone_id] = self.process(
                recording_logs=recording_logs,
                zone_id=zone_id,
            )

        return results

    def detect_stable_periods(
        self,
        recording_logs: List[dict],
        window_size: int = 5,
    ) -> Tuple[List[int], List[int]]:
        """
        안정적인 구간 감지.

        Recording 데이터에서 무게가 안정적인 구간의 인덱스를 찾습니다.
        Baseline과 Current 결정에 활용할 수 있습니다.

        Args:
            recording_logs: Recording 로그 리스트
            window_size: 안정성 체크 윈도우 크기

        Returns:
            (baseline_indices, current_indices): 안정 구간 인덱스 튜플
        """
        if len(recording_logs) < window_size * 2:
            # 데이터 부족 시 기본값 반환
            return (
                list(range(min(window_size, len(recording_logs)))),
                list(range(max(0, len(recording_logs) - window_size), len(recording_logs))),
            )

        # 모든 샘플 파싱
        parsed_logs = []
        for log in recording_logs:
            loadcells = log.get("loadcells", [])
            if len(loadcells) >= 10:
                parsed_values = [self._parse_loadcell_value(v) for v in loadcells[:10]]
                parsed_logs.append(parsed_values)

        if len(parsed_logs) < window_size * 2:
            return (
                list(range(min(window_size, len(parsed_logs)))),
                list(range(max(0, len(parsed_logs) - window_size), len(parsed_logs))),
            )

        # 윈도우별 변동성 계산
        variances = []
        for i in range(len(parsed_logs) - window_size + 1):
            window = parsed_logs[i:i + window_size]
            # 각 채널의 최대-최소 차이 합산
            variance = sum(
                max(w[ch] for w in window) - min(w[ch] for w in window)
                for ch in range(10)
            )
            variances.append(variance)

        # 안정 구간 찾기 (변동성이 임계값 이하인 구간)
        stable_threshold = self.stability_threshold * 10 * window_size

        # 초반 안정 구간 (Baseline용)
        baseline_indices = []
        for i, var in enumerate(variances[:len(variances) // 2]):
            if var <= stable_threshold:
                baseline_indices.extend(range(i, i + window_size))
                break

        if not baseline_indices:
            baseline_indices = list(range(window_size))

        # 후반 안정 구간 (Current용)
        current_indices = []
        for i in range(len(variances) - 1, len(variances) // 2, -1):
            if variances[i] <= stable_threshold:
                current_indices.extend(range(i, i + window_size))
                break

        if not current_indices:
            current_indices = list(range(len(parsed_logs) - window_size, len(parsed_logs)))

        return (
            sorted(set(baseline_indices)),
            sorted(set(current_indices)),
        )

    def _parse_loadcell_value(self, value: str) -> float:
        """
        로드셀 값 파싱.

        Args:
            value: 로드셀 문자열 값 (예: "+01234", "-00567", "EEEEEE")

        Returns:
            무게 값 (g), 파싱 실패 시 0.0
        """
        if not value:
            return 0.0

        # 에러 상태 체크 (EEEEEE, VVVVVV 등)
        if value.upper().startswith(("E", "V", "X")):
            logger.debug(f"Loadcell error state: {value}")
            return 0.0

        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse loadcell value: {value}")
            return 0.0

    def _calculate_average(self, samples: List[List[float]]) -> List[float]:
        """
        샘플 평균 계산.

        Args:
            samples: 로드셀 값 리스트의 리스트 [[ch0, ch1, ...], ...]

        Returns:
            채널별 평균 값 리스트
        """
        if not samples:
            return [0.0] * 10

        num_channels = len(samples[0])
        averages = []

        for ch in range(num_channels):
            ch_values = [s[ch] for s in samples if ch < len(s)]
            if ch_values:
                averages.append(sum(ch_values) / len(ch_values))
            else:
                averages.append(0.0)

        return averages


def convert_to_weight_data(
    processed: ProcessedWeightData,
) -> dict:
    """
    ProcessedWeightData를 API WeightData 형식으로 변환.

    Args:
        processed: ProcessedWeightData 인스턴스

    Returns:
        WeightData 호환 딕셔너리
    """
    return {
        "before_weights": processed.before_weights,
        "after_weights": processed.after_weights,
        "delta_weight": processed.delta_weight,
        "channels": processed.channels,
    }
