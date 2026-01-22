"""
Advanced Test Scenarios.

성능평가 테스트 시나리오 규격 1.1v 기반 테스트.

시나리오:
- 시나리오 4: 다수인원 동시취출 (3명까지)
- 시나리오 5: 상품 선택 및 반납 인식
- 시나리오 6: 상품 진열 변경 후 구매
- 시나리오 7: 도어 장기 오픈 후 취출 (1~5분)
- 시나리오 8: 상품 연속 취출 (2~10개, 빠른 속도)

실행:
    cd Edge_Environment/services/model
    python -m pytest tests/test_advanced_scenarios.py -v
"""

import pytest
import time
from typing import List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Components under test
from vision.multi_hand_detector import MultiHandDetector, HandCluster
from vision.yolo_wrapper import YOLODetection
from engine.event_tracker import EventTracker, EventDirection
from engine.advanced import (
    ReturnDetector,
    CrossZoneDetector,
    BaselineManager,
    RapidPickupHandler,
)
from weight import MultiZoneWeightMonitor


# ========== Fixtures ==========

@pytest.fixture
def multi_hand_detector():
    return MultiHandDetector(max_distance_px=150.0)


@pytest.fixture
def return_detector():
    return ReturnDetector(match_tolerance=0.15, time_window=30.0)


@pytest.fixture
def event_tracker():
    return EventTracker(max_history=100)


@pytest.fixture
def cross_zone_detector():
    return CrossZoneDetector(tolerance=0.10, min_weight=10.0)


@pytest.fixture
def baseline_manager():
    return BaselineManager(drift_rate=0.5, refresh_interval=60.0)


@pytest.fixture
def rapid_pickup_handler():
    return RapidPickupHandler(buffer_window=3.0, settling_threshold=5.0)


@pytest.fixture
def multi_zone_monitor():
    return MultiZoneWeightMonitor(zone_count=5, change_threshold=5.0)


def make_detection(
    x1: float, y1: float, x2: float, y2: float,
    conf: float, cls: int, name: str
) -> YOLODetection:
    """테스트용 YOLODetection 생성."""
    return YOLODetection(
        xyxy=(x1, y1, x2, y2),
        conf=conf,
        cls=cls,
        name=name,
    )


# ========== 시나리오 4: 다수인원 동시취출 ==========

class TestMultiPersonPickup:
    """시나리오 4: 다수인원 동시취출 (3명까지)."""

    def test_two_persons_simultaneous(self, multi_hand_detector):
        """2명 동시 취출 테스트."""
        detections = [
            # Person 1: 손 + 상품
            make_detection(100, 100, 150, 150, 0.9, 0, "hand"),
            make_detection(110, 110, 160, 160, 0.8, 26, "chickenmayo_rice"),
            # Person 2: 손 + 상품
            make_detection(400, 100, 450, 150, 0.85, 0, "hand"),
            make_detection(410, 110, 460, 160, 0.75, 9, "vita500"),
        ]

        result = multi_hand_detector.filter(detections)

        assert result.person_count == 2
        assert result.total_hands == 2
        assert len(result.assigned_products) == 2

    def test_three_persons_different_shelves(self, multi_hand_detector):
        """3명 다른 선반에서 동시 취출 테스트."""
        # 손 클러스터링 거리가 200px이므로 각 손을 최소 250px 이상 떨어뜨림
        detections = [
            # Person 1: Zone 0 (y=50)
            make_detection(100, 50, 150, 100, 0.9, 0, "hand"),
            make_detection(110, 60, 160, 110, 0.8, 26, "chickenmayo_rice"),
            # Person 2: Zone 2 (y=350, 250px+ 떨어짐)
            make_detection(100, 350, 150, 400, 0.88, 0, "hand"),
            make_detection(110, 360, 160, 410, 0.77, 9, "vita500"),
            # Person 3: Zone 4 (y=650, 250px+ 떨어짐)
            make_detection(100, 650, 150, 700, 0.85, 0, "hand"),
            make_detection(110, 660, 160, 710, 0.72, 15, "samdasoo_500"),
        ]

        result = multi_hand_detector.filter(detections)

        assert result.person_count == 3
        assert result.total_hands == 3
        assert len(result.assigned_products) == 3

    def test_two_hands_same_person(self, multi_hand_detector):
        """같은 사람의 두 손 감지 (클러스터링)."""
        detections = [
            # Same person, two hands close together
            make_detection(100, 100, 150, 150, 0.9, 0, "hand"),
            make_detection(180, 100, 230, 150, 0.88, 0, "hand"),  # Close to first
            make_detection(120, 110, 170, 160, 0.8, 26, "chickenmayo_rice"),
        ]

        result = multi_hand_detector.filter(detections)

        # Should be clustered as 1 person with 2 hands
        assert result.person_count == 1
        assert result.total_hands == 2
        assert len(result.hand_clusters[0].hands) == 2


# ========== 시나리오 5: 상품 선택 및 반납 인식 ==========

class TestProductReturn:
    """시나리오 5: 상품 선택 및 반납 인식."""

    def test_same_position_return(self, return_detector):
        """같은 위치에 반납."""
        # 픽업 기록
        return_detector.record_pickup(
            zone_id=0,
            weight=365.0,
            product_id=26,
            product_name="chickenmayo_rice",
        )

        # 같은 Zone에 반납
        result = return_detector.check_return(
            zone_id=0,
            positive_delta=365.0,
        )

        assert result.is_return is True
        assert result.match_score > 0.9
        assert result.should_cancel_payment is True
        assert result.return_type == "same_position"

    def test_horizontal_position_change(self, return_detector):
        """수평 이동 후 반납 (인접 Zone)."""
        # Zone 0에서 픽업
        return_detector.record_pickup(zone_id=0, weight=365.0)

        # Zone 1에 반납 (수평 이동)
        result = return_detector.check_return(
            zone_id=1,
            positive_delta=365.0,
        )

        assert result.is_return is True
        assert result.return_type == "horizontal_move"

    def test_cross_shelf_return(self, return_detector):
        """다른 선반에 반납 (수직 이동)."""
        # Zone 0에서 픽업
        return_detector.record_pickup(zone_id=0, weight=365.0)

        # Zone 3에 반납 (다른 선반)
        result = return_detector.check_return(
            zone_id=3,
            positive_delta=365.0,
        )

        assert result.is_return is True
        assert result.return_type == "cross_shelf"

    def test_weight_mismatch_not_return(self, return_detector):
        """무게 불일치 시 반납 아님."""
        # 365g 픽업
        return_detector.record_pickup(zone_id=0, weight=365.0)

        # 다른 무게로 반납 시도 (520g)
        result = return_detector.check_return(
            zone_id=0,
            positive_delta=520.0,
        )

        # 무게 차이가 크면 반납으로 인정 안 됨
        assert result.is_return is False

    def test_timeout_not_return(self, return_detector):
        """시간 초과 후 반납 아님."""
        # 픽업 기록
        return_detector.record_pickup(zone_id=0, weight=365.0)

        # 픽업 이벤트의 타임스탬프를 과거로 조작
        return_detector.recent_pickups[0].timestamp = time.time() - 60.0

        # 시간 초과 후 반납
        result = return_detector.check_return(
            zone_id=0,
            positive_delta=365.0,
        )

        # 시간 윈도우 초과로 반납 인정 안 됨
        assert result.is_return is False


# ========== 시나리오 6: 상품 진열 변경 후 구매 ==========

class TestDisplayChange:
    """시나리오 6: 상품 진열 변경 후 구매."""

    def test_horizontal_move_detected(self, cross_zone_detector):
        """수평 이동 감지."""
        zone_deltas = [
            (0, -365.0),  # Zone 0에서 빠짐
            (1, +365.0),  # Zone 1에 추가됨
        ]

        result = cross_zone_detector.detect(zone_deltas)

        assert result.is_movement is True
        assert result.source_zone == 0
        assert result.target_zone == 1
        assert result.movement_type == "horizontal"
        assert result.should_skip_payment is True

    def test_vertical_move_detected(self, cross_zone_detector):
        """수직 이동 감지."""
        zone_deltas = [
            (0, -520.0),  # Zone 0에서 빠짐
            (3, +520.0),  # Zone 3에 추가됨
        ]

        result = cross_zone_detector.detect(zone_deltas)

        assert result.is_movement is True
        assert result.source_zone == 0
        assert result.target_zone == 3
        assert result.movement_type == "vertical"

    def test_pickup_not_movement(self, cross_zone_detector):
        """순수 픽업은 이동 아님."""
        zone_deltas = [
            (0, -365.0),  # Zone 0에서만 빠짐
        ]

        result = cross_zone_detector.detect(zone_deltas)

        assert result.is_movement is False

    def test_weight_mismatch_not_movement(self, cross_zone_detector):
        """무게 불일치 시 이동 아님."""
        zone_deltas = [
            (0, -365.0),  # Zone 0에서 빠짐
            (1, +520.0),  # Zone 1에 다른 무게 추가
        ]

        result = cross_zone_detector.detect(zone_deltas)

        # 무게 차이가 허용 오차 초과
        assert result.is_movement is False


# ========== 시나리오 7: 도어 장기 오픈 후 취출 ==========

class TestLongDoorOpen:
    """시나리오 7: 도어 장기 오픈 후 취출 (1~5분)."""

    def test_1min_open_pickup(self, baseline_manager):
        """1분 오픈 후 취출."""
        baseline_manager.set_baseline(zone_id=0, weight=1000.0)

        # 1분 후 취출 (935g = 1000 - 65g 드리프트 추정 - 실제 픽업 360g)
        corrected = baseline_manager.get_corrected_delta(
            zone_id=0,
            current_weight=635.0,  # 1000 - 365
            elapsed_time=60.0,  # 1분
        )

        # 드리프트 보정: 0.5g/min * 1min = 0.5g
        # 실제 변화: 635 - 1000 = -365g
        # 보정 후: -365 + 0.5 ≈ -364.5g
        assert abs(corrected) > 360  # 여전히 유의미한 픽업

    def test_3min_open_pickup(self, baseline_manager):
        """3분 오픈 후 취출."""
        baseline_manager.set_baseline(zone_id=0, weight=1000.0)

        corrected = baseline_manager.get_corrected_delta(
            zone_id=0,
            current_weight=635.0,
            elapsed_time=180.0,  # 3분
        )

        # 드리프트 보정: 0.5g/min * 3min = 1.5g
        assert abs(corrected) > 360

    def test_5min_open_drift_correction(self, baseline_manager):
        """5분 오픈 후 드리프트 보정."""
        baseline_manager.set_baseline(zone_id=0, weight=1000.0)

        corrected = baseline_manager.get_corrected_delta(
            zone_id=0,
            current_weight=635.0,
            elapsed_time=300.0,  # 5분
        )

        # 드리프트 보정: 0.5g/min * 5min = 2.5g
        assert abs(corrected) > 360

    def test_refresh_baseline_after_long_open(self, baseline_manager):
        """장시간 오픈 후 baseline 갱신."""
        baseline_manager.set_baseline(zone_id=0, weight=1000.0)

        # 갱신 필요 여부 확인 (60초 이후)
        assert baseline_manager.should_refresh(
            zone_id=0,
            current_time=time.time() + 70.0,
        )

        # baseline 갱신
        baseline_manager.refresh_baseline(zone_id=0, current_weight=1002.0)

        # 새 baseline 확인
        status = baseline_manager.get_zone_status(0)
        assert status["baseline"] == 1002.0


# ========== 시나리오 8: 상품 연속 취출 ==========

class TestRapidPickup:
    """시나리오 8: 상품 연속 취출 (2~10개, 빠른 속도)."""

    def test_2_items_2_seconds(self, rapid_pickup_handler):
        """2개 상품 2초 내 취출."""
        base_time = time.time()

        # 첫 번째 상품
        rapid_pickup_handler.add_event(
            delta_weight=-365.0,
            timestamp=base_time,
        )

        # 두 번째 상품 (1초 후)
        rapid_pickup_handler.add_event(
            delta_weight=-520.0,
            timestamp=base_time + 1.0,
        )

        # 버퍼 확인
        assert len(rapid_pickup_handler.event_buffer) == 2
        assert rapid_pickup_handler.get_cumulative_delta() == -885.0

    def test_5_items_5_seconds(self, rapid_pickup_handler):
        """5개 상품 5초 내 취출."""
        base_time = time.time()
        weights = [-365.0, -520.0, -130.0, -200.0, -150.0]

        for i, weight in enumerate(weights):
            rapid_pickup_handler.add_event(
                delta_weight=weight,
                timestamp=base_time + i,
            )

        assert len(rapid_pickup_handler.event_buffer) == 5
        assert rapid_pickup_handler.get_cumulative_delta() == sum(weights)

    def test_10_items_10_seconds(self, rapid_pickup_handler):
        """10개 상품 10초 내 취출."""
        base_time = time.time()
        weights = [-100.0] * 10  # 각 100g

        for i, weight in enumerate(weights):
            rapid_pickup_handler.add_event(
                delta_weight=weight,
                timestamp=base_time + i,
            )

        assert len(rapid_pickup_handler.event_buffer) == 10
        assert rapid_pickup_handler.get_cumulative_delta() == -1000.0

    def test_settling_detection(self, rapid_pickup_handler):
        """안정화 감지."""
        base_time = time.time()

        rapid_pickup_handler.add_event(delta_weight=-365.0, timestamp=base_time)

        # 바로 후에는 안정화 안 됨
        assert rapid_pickup_handler.is_settled(base_time + 0.5) is False

        # 충분한 시간 후 안정화됨
        assert rapid_pickup_handler.is_settled(base_time + 2.0) is True

    def test_flush_buffer(self, rapid_pickup_handler):
        """버퍼 플러시."""
        base_time = time.time()

        rapid_pickup_handler.add_event(delta_weight=-365.0, timestamp=base_time)
        rapid_pickup_handler.add_event(delta_weight=-520.0, timestamp=base_time + 0.5)

        result = rapid_pickup_handler.flush_buffer()

        assert result.event_count == 2
        assert result.total_delta == -885.0
        assert result.is_complete is True

        # 버퍼 비워짐
        assert len(rapid_pickup_handler.event_buffer) == 0


# ========== 추가 통합 테스트 ==========

class TestEventTracker:
    """이벤트 추적기 테스트."""

    def test_add_pickup_event(self, event_tracker):
        """픽업 이벤트 추가."""
        event = event_tracker.add_event(
            zone_id=0,
            delta_weight=-365.0,
            product_id=26,
            product_name="chickenmayo_rice",
        )

        assert event.direction == EventDirection.PICKUP
        assert event.delta_weight == -365.0
        assert event.product_name == "chickenmayo_rice"

    def test_add_return_event(self, event_tracker):
        """반납 이벤트 추가."""
        event = event_tracker.add_event(
            zone_id=0,
            delta_weight=365.0,  # 양수
        )

        assert event.direction == EventDirection.RETURN

    def test_detect_return_match(self, event_tracker):
        """반납 매칭 감지."""
        # 픽업
        event_tracker.add_event(zone_id=0, delta_weight=-365.0)

        # 반납
        return_event = event_tracker.add_event(zone_id=0, delta_weight=365.0)

        result = event_tracker.detect_return(return_event)

        assert result.is_return is True
        assert result.weight_match_score > 0.9


class TestMultiZoneMonitor:
    """다중 Zone 모니터 테스트."""

    def test_zone_update(self, multi_zone_monitor):
        """Zone 무게 업데이트."""
        multi_zone_monitor.set_baseline(0, 1000.0)

        event = multi_zone_monitor.update(0, 635.0)

        assert event is not None
        assert event.delta_weight == -365.0

    def test_cross_zone_detection(self, multi_zone_monitor):
        """Cross-Zone 이동 감지."""
        multi_zone_monitor.set_baseline(0, 1000.0)
        multi_zone_monitor.set_baseline(1, 500.0)

        multi_zone_monitor.update(0, 635.0)  # -365
        multi_zone_monitor.update(1, 865.0)  # +365

        result = multi_zone_monitor.detect_cross_zone_movement()

        assert result.detected is True
        assert result.source_zone == 0
        assert result.target_zone == 1

    def test_loadcell_update(self, multi_zone_monitor):
        """로드셀 데이터로 업데이트."""
        baseline = [500, 500, 0, 0, 0, 0, 0, 0, 0, 0]
        current = [135, 500, 0, 0, 0, 0, 0, 0, 0, 0]  # Zone 0: -365

        multi_zone_monitor.set_baselines_from_loadcell(baseline)
        events = multi_zone_monitor.update_from_loadcell(current)

        assert events[0] is not None
        assert events[0].delta_weight == -365.0
