"""
Cross-Zone Detector.

상품 진열 위치 변경 감지 (시나리오 6).

핵심 기능:
1. 동시 발생한 음수/양수 무게 변화 쌍 감지
2. 무게 유사도로 동일 상품 판정
3. 진열 변경 이벤트 생성 (결제 안 함)

사용 예시:
    detector = CrossZoneDetector(tolerance=0.10)
    result = detector.detect(zone_deltas)
    if result.is_movement:
        # 진열 변경으로 판정, 결제 스킵
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class MovementResult:
    """
    진열 변경 감지 결과.

    Attributes:
        is_movement: 진열 변경 여부
        source_zone: 출발 Zone ID
        target_zone: 도착 Zone ID
        weight: 이동 무게 (g)
        weight_match_score: 무게 매칭 점수
        movement_type: 이동 유형 (horizontal, vertical, cross)
        should_skip_payment: 결제 스킵 여부
    """
    is_movement: bool = False
    source_zone: int = -1
    target_zone: int = -1
    weight: float = 0.0
    weight_match_score: float = 0.0
    movement_type: str = "none"
    should_skip_payment: bool = False

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "is_movement": self.is_movement,
            "source_zone": self.source_zone,
            "target_zone": self.target_zone,
            "weight": round(self.weight, 1),
            "weight_match_score": round(self.weight_match_score, 3),
            "movement_type": self.movement_type,
            "should_skip_payment": self.should_skip_payment,
        }


class CrossZoneDetector:
    """
    진열 변경 감지기.

    A Zone에서 무게 감소, B Zone에서 유사한 무게 증가 시
    상품 진열 변경으로 판단합니다.

    Attributes:
        tolerance: 무게 매칭 허용 오차 (비율)
        min_weight: 최소 무게 변화량 (g)
        zone_count: Zone 수
    """

    def __init__(
        self,
        tolerance: float = 0.10,
        min_weight: float = 10.0,
        zone_count: int = 5,
    ):
        """
        감지기 초기화.

        Args:
            tolerance: 무게 매칭 허용 오차 (비율)
            min_weight: 최소 무게 변화량 (g)
            zone_count: Zone 수
        """
        self.tolerance = tolerance
        self.min_weight = min_weight
        self.zone_count = zone_count

    def detect(
        self,
        zone_deltas: List[Tuple[int, float]],
    ) -> MovementResult:
        """
        진열 변경 감지.

        Args:
            zone_deltas: [(zone_id, delta_weight), ...] 리스트

        Returns:
            MovementResult
        """
        # 음수/양수 변화 Zone 분리
        negative_zones: List[Tuple[int, float]] = []  # 무게 감소
        positive_zones: List[Tuple[int, float]] = []  # 무게 증가

        for zone_id, delta in zone_deltas:
            if delta < -self.min_weight:
                negative_zones.append((zone_id, delta))
            elif delta > self.min_weight:
                positive_zones.append((zone_id, delta))

        # 매칭 가능한 쌍이 없으면 종료
        if not negative_zones or not positive_zones:
            return MovementResult(is_movement=False)

        # 최적 매칭 찾기
        best_match = None
        best_score = 0.0

        for neg_zone, neg_delta in negative_zones:
            neg_weight = abs(neg_delta)

            for pos_zone, pos_delta in positive_zones:
                pos_weight = pos_delta

                # 무게 차이 계산
                weight_diff = abs(neg_weight - pos_weight)
                max_diff = neg_weight * self.tolerance

                if weight_diff <= max_diff:
                    # 매칭 점수 계산
                    score = 1.0 - (weight_diff / neg_weight) if neg_weight > 0 else 0

                    # 이동 유형 결정
                    movement_type = self._determine_movement_type(neg_zone, pos_zone)

                    if score > best_score:
                        best_score = score
                        best_match = (neg_zone, pos_zone, neg_weight, movement_type)

        if best_match and best_score >= 0.8:  # 높은 매칭 점수 요구
            source_zone, target_zone, weight, movement_type = best_match

            logger.info(
                f"Display movement detected: Zone {source_zone} -> Zone {target_zone}, "
                f"weight={weight:.1f}g, type={movement_type}, score={best_score:.3f}"
            )

            return MovementResult(
                is_movement=True,
                source_zone=source_zone,
                target_zone=target_zone,
                weight=weight,
                weight_match_score=best_score,
                movement_type=movement_type,
                should_skip_payment=True,
            )

        return MovementResult(is_movement=False)

    def detect_from_loadcell(
        self,
        current_weights: List[float],
        baseline_weights: List[float],
    ) -> MovementResult:
        """
        10채널 로드셀 데이터에서 진열 변경 감지.

        Args:
            current_weights: 현재 무게 (10채널)
            baseline_weights: 기준 무게 (10채널)

        Returns:
            MovementResult
        """
        # Zone별 delta 계산
        zone_deltas = []

        for zone_id in range(self.zone_count):
            start_idx = zone_id * 2
            current_zone = sum(current_weights[start_idx:start_idx + 2])
            baseline_zone = sum(baseline_weights[start_idx:start_idx + 2])
            delta = current_zone - baseline_zone
            zone_deltas.append((zone_id, delta))

        return self.detect(zone_deltas)

    def _determine_movement_type(self, source_zone: int, target_zone: int) -> str:
        """
        이동 유형 결정.

        Args:
            source_zone: 출발 Zone
            target_zone: 도착 Zone

        Returns:
            이동 유형 문자열
        """
        zone_diff = abs(source_zone - target_zone)

        if zone_diff == 0:
            return "same_zone"  # 같은 Zone 내 이동 (거의 없음)
        elif zone_diff == 1:
            return "horizontal"  # 인접 선반 이동
        else:
            return "vertical"  # 원거리 선반 이동

    def analyze_multi_zone_changes(
        self,
        zone_deltas: List[Tuple[int, float]],
    ) -> dict:
        """
        다중 Zone 변화 분석.

        Args:
            zone_deltas: [(zone_id, delta_weight), ...] 리스트

        Returns:
            분석 결과 딕셔너리
        """
        # 변화 분류
        pickups = []    # 픽업 (음수)
        returns = []    # 반납 (양수)
        no_change = []  # 변화 없음

        for zone_id, delta in zone_deltas:
            if delta < -self.min_weight:
                pickups.append((zone_id, delta))
            elif delta > self.min_weight:
                returns.append((zone_id, delta))
            else:
                no_change.append((zone_id, delta))

        # 이동 매칭 시도
        movements = []
        remaining_pickups = list(pickups)
        remaining_returns = list(returns)

        while remaining_pickups and remaining_returns:
            best_pair = None
            best_score = 0.0

            for i, (p_zone, p_delta) in enumerate(remaining_pickups):
                for j, (r_zone, r_delta) in enumerate(remaining_returns):
                    weight_diff = abs(abs(p_delta) - r_delta)
                    max_diff = abs(p_delta) * self.tolerance

                    if weight_diff <= max_diff:
                        score = 1.0 - (weight_diff / abs(p_delta))
                        if score > best_score:
                            best_score = score
                            best_pair = (i, j, p_zone, r_zone, abs(p_delta))

            if best_pair and best_score >= 0.8:
                i, j, src, dst, weight = best_pair
                movements.append({
                    "source_zone": src,
                    "target_zone": dst,
                    "weight": weight,
                    "score": best_score,
                })
                remaining_pickups.pop(i)
                remaining_returns.pop(j)
            else:
                break

        return {
            "total_zones": len(zone_deltas),
            "pickups": [{"zone": z, "delta": d} for z, d in remaining_pickups],
            "returns": [{"zone": z, "delta": d} for z, d in remaining_returns],
            "movements": movements,
            "movement_count": len(movements),
            "has_unmatched_activity": bool(remaining_pickups or remaining_returns),
        }
