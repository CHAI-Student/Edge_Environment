"""
Zone Detector.

채널 인덱스에서 Zone ID를 감지합니다.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
import logging

from ..config import ZONE_CHANNEL_MAP

logger = logging.getLogger(__name__)


@dataclass
class ZoneChangeInfo:
    """Zone 변화 정보."""

    zone_id: int
    channels: List[int]  # 이 Zone에서 변화 감지된 채널들
    delta: float  # 이 Zone의 총 무게 변화량
    is_removal: bool  # 제거 여부 (음수 변화)


class ZoneDetector:
    """
    Zone 감지기.

    loadcell.change 이벤트에서 Zone을 감지합니다.
    """

    def __init__(self, zone_channel_map: Optional[Dict[int, List[int]]] = None):
        """
        초기화.

        Args:
            zone_channel_map: Zone-Channel 매핑 (기본값: config의 매핑 사용)
        """
        self.zone_channel_map = zone_channel_map or ZONE_CHANNEL_MAP

        # 역매핑 생성 (channel -> zone)
        self.channel_zone_map: Dict[int, int] = {}
        for zone_id, channels in self.zone_channel_map.items():
            for ch in channels:
                self.channel_zone_map[ch] = zone_id

    def detect_zones(
        self,
        changed_indices: List[int],
        old_values: List[float],
        new_values: List[float],
    ) -> List[ZoneChangeInfo]:
        """
        변화 감지된 채널들에서 Zone 정보 추출.

        Args:
            changed_indices: 변화 감지된 채널 인덱스
            old_values: 이전 값들
            new_values: 새 값들

        Returns:
            ZoneChangeInfo 리스트
        """
        # Zone별 변화 집계
        zone_changes: Dict[int, Dict] = {}

        for i, ch_idx in enumerate(changed_indices):
            zone_id = self.channel_zone_map.get(ch_idx)
            if zone_id is None:
                logger.warning(f"Channel {ch_idx} not mapped to any zone")
                continue

            if zone_id not in zone_changes:
                zone_changes[zone_id] = {
                    "channels": [],
                    "delta": 0.0,
                }

            zone_changes[zone_id]["channels"].append(ch_idx)

            # 델타 계산 (새 값 - 이전 값)
            if i < len(old_values) and i < len(new_values):
                zone_changes[zone_id]["delta"] += (new_values[i] - old_values[i])

        # ZoneChangeInfo 리스트 생성
        results = []
        for zone_id, info in zone_changes.items():
            change_info = ZoneChangeInfo(
                zone_id=zone_id,
                channels=info["channels"],
                delta=info["delta"],
                is_removal=info["delta"] < 0,
            )
            results.append(change_info)
            logger.info(
                f"Zone {zone_id} detected: delta={info['delta']:.1f}g, "
                f"channels={info['channels']}, removal={change_info.is_removal}"
            )

        return results

    def get_primary_zone(
        self,
        changed_indices: List[int],
        old_values: List[float],
        new_values: List[float],
    ) -> Optional[ZoneChangeInfo]:
        """
        가장 큰 변화가 있는 Zone 반환.

        Args:
            changed_indices: 변화 감지된 채널 인덱스
            old_values: 이전 값들
            new_values: 새 값들

        Returns:
            가장 큰 변화가 있는 Zone 또는 None
        """
        zones = self.detect_zones(changed_indices, old_values, new_values)
        if not zones:
            return None

        # 절대 델타가 가장 큰 Zone 반환
        return max(zones, key=lambda z: abs(z.delta))

    def is_single_zone_event(self, changed_indices: List[int]) -> bool:
        """
        단일 Zone 이벤트인지 확인.

        Args:
            changed_indices: 변화 감지된 채널 인덱스

        Returns:
            단일 Zone 이벤트이면 True
        """
        zones = set()
        for ch_idx in changed_indices:
            zone_id = self.channel_zone_map.get(ch_idx)
            if zone_id is not None:
                zones.add(zone_id)

        return len(zones) == 1
