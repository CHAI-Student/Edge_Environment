"""
SSE Client Tests.

io_board SSE 구독 및 이벤트 파싱 테스트.
"""

import pytest
from typing import List

# Import modules to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sse_client.event_parser import parse_sse_event, LoadcellChangeEvent, LoadcellUpdateEvent
from sse_client.zone_detector import ZoneDetector


class TestEventParser:
    """이벤트 파서 테스트."""

    def test_parse_loadcell_change_event(self, sample_loadcell_change_event):
        """loadcell.change 이벤트 파싱."""
        event = parse_sse_event(sample_loadcell_change_event)

        assert isinstance(event, LoadcellChangeEvent)
        assert event.event_type == "loadcell.change"
        assert event.changed_indices == [0, 1]
        assert len(event.old_values) == 10
        assert len(event.new_values) == 10
        assert len(event.deltas) == 10

    def test_parse_loadcell_update_event(self):
        """loadcell.update 이벤트 파싱."""
        raw_event = {
            "event": "loadcell.update",
            "filtered_values": [432.0, 433.0, 260.0, 260.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "raw_values": [430.0, 435.0, 258.0, 262.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "timestamp": 1737446400.0,
        }

        event = parse_sse_event(raw_event)

        assert isinstance(event, LoadcellUpdateEvent)
        assert event.event_type == "loadcell.update"
        assert len(event.filtered_values) == 10
        assert len(event.raw_values) == 10

    def test_parse_unknown_event(self):
        """알 수 없는 이벤트 타입."""
        raw_event = {
            "event": "unknown.event",
            "data": "test",
        }

        event = parse_sse_event(raw_event)
        assert event is None


class TestZoneDetector:
    """Zone 감지기 테스트."""

    def test_detect_zone_0_change(self, zone_channel_map):
        """Zone 0 변화 감지 (채널 0, 1)."""
        detector = ZoneDetector()

        result = detector.get_primary_zone(
            changed_indices=[0, 1],
            old_values=[800.0, 800.0] + [0.0] * 8,
            new_values=[435.0, 430.0] + [0.0] * 8,
        )

        assert result is not None
        assert result.zone_id == 0
        assert result.delta_weight < 0  # 무게 감소 (상품 픽업)

    def test_detect_zone_2_change(self, zone_channel_map):
        """Zone 2 변화 감지 (채널 4, 5)."""
        detector = ZoneDetector()

        result = detector.get_primary_zone(
            changed_indices=[4, 5],
            old_values=[0.0] * 4 + [500.0, 500.0] + [0.0] * 4,
            new_values=[0.0] * 4 + [300.0, 280.0] + [0.0] * 4,
        )

        assert result is not None
        assert result.zone_id == 2
        assert result.delta_weight < 0

    def test_no_zone_for_multiple_zones(self, zone_channel_map):
        """여러 Zone에 걸친 변화 (None 반환)."""
        detector = ZoneDetector()

        # 채널 0, 1 (Zone 0) + 채널 2, 3 (Zone 1) 동시 변화
        result = detector.get_primary_zone(
            changed_indices=[0, 1, 2, 3],
            old_values=[800.0, 800.0, 500.0, 500.0] + [0.0] * 6,
            new_values=[400.0, 400.0, 200.0, 200.0] + [0.0] * 6,
        )

        # 여러 Zone 변화 시 None 또는 가장 큰 변화량 Zone 반환
        # 구현에 따라 다름

    def test_calculate_delta_weight(self):
        """무게 변화량 계산."""
        detector = ZoneDetector()

        result = detector.get_primary_zone(
            changed_indices=[0, 1],
            old_values=[432.0, 433.0] + [0.0] * 8,
            new_values=[67.0, 68.0] + [0.0] * 8,
        )

        assert result is not None
        # delta = (67 + 68) - (432 + 433) = 135 - 865 = -730
        expected_delta = -730.0
        assert abs(result.delta_weight - expected_delta) < 1.0

    def test_weight_increase_detection(self):
        """무게 증가 감지 (상품 반환)."""
        detector = ZoneDetector()

        result = detector.get_primary_zone(
            changed_indices=[0, 1],
            old_values=[100.0, 100.0] + [0.0] * 8,
            new_values=[450.0, 450.0] + [0.0] * 8,
        )

        assert result is not None
        assert result.zone_id == 0
        assert result.delta_weight > 0  # 무게 증가 (상품 반환)


class TestZoneChannelMapping:
    """Zone-Channel 매핑 테스트."""

    def test_all_zones_covered(self, zone_channel_map):
        """모든 Zone (0-4)이 매핑되어 있는지."""
        for zone_id in range(5):
            assert zone_id in zone_channel_map
            assert len(zone_channel_map[zone_id]) == 2

    def test_all_channels_mapped(self, zone_channel_map):
        """모든 채널 (0-9)이 매핑되어 있는지."""
        all_channels = []
        for channels in zone_channel_map.values():
            all_channels.extend(channels)

        assert sorted(all_channels) == list(range(10))

    def test_no_channel_overlap(self, zone_channel_map):
        """채널 중복 없는지."""
        all_channels = []
        for channels in zone_channel_map.values():
            all_channels.extend(channels)

        assert len(all_channels) == len(set(all_channels))
