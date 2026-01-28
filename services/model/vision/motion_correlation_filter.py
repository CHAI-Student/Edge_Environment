"""
Motion Correlation Filter.

손과 상품의 움직임 상관관계를 분석하여 가산점 부여.

알고리즘:
1. 연속 프레임에서 손과 상품의 중심점 추적
2. 각 객체의 이동 벡터(velocity) 계산
3. 손과 상품의 이동 벡터 유사도 계산 (코사인 유사도 + 크기 유사도)
4. 높은 상관관계 → motion_bonus 부여

핵심 아이디어:
- 손이 상품을 잡고 있으면, 손과 상품은 함께 움직임
- 이동 벡터가 유사한 방향 + 유사한 크기 → 높은 상관관계
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import deque
import math
import logging
import time

from .yolo_wrapper import YOLODetection

logger = logging.getLogger(__name__)


@dataclass
class MotionVector:
    """이동 벡터."""
    dx: float  # X 방향 이동량 (픽셀)
    dy: float  # Y 방향 이동량 (픽셀)

    @property
    def magnitude(self) -> float:
        """벡터 크기."""
        return math.sqrt(self.dx ** 2 + self.dy ** 2)

    @property
    def is_significant(self) -> float:
        """의미 있는 움직임인지 (최소 이동량 체크)."""
        return self.magnitude >= 3.0  # 최소 3픽셀 이동

    def cosine_similarity(self, other: "MotionVector") -> float:
        """다른 벡터와의 코사인 유사도 (-1.0 ~ 1.0)."""
        dot = self.dx * other.dx + self.dy * other.dy
        mag_product = self.magnitude * other.magnitude

        if mag_product < 0.001:  # 거의 움직임 없음
            return 0.0

        return dot / mag_product

    def magnitude_similarity(self, other: "MotionVector") -> float:
        """다른 벡터와의 크기 유사도 (0.0 ~ 1.0)."""
        if self.magnitude < 0.001 and other.magnitude < 0.001:
            return 1.0  # 둘 다 정지

        max_mag = max(self.magnitude, other.magnitude)
        if max_mag < 0.001:
            return 1.0

        min_mag = min(self.magnitude, other.magnitude)
        return min_mag / max_mag


@dataclass
class TrackedObject:
    """추적 중인 객체."""
    class_id: int
    class_name: str
    positions: deque = field(default_factory=lambda: deque(maxlen=10))  # 최근 10프레임
    timestamps: deque = field(default_factory=lambda: deque(maxlen=10))
    last_confidence: float = 0.0

    def add_position(self, center_x: float, center_y: float, timestamp: float, confidence: float):
        """위치 추가."""
        self.positions.append((center_x, center_y))
        self.timestamps.append(timestamp)
        self.last_confidence = confidence

    def get_motion_vector(self, lookback_frames: int = 3) -> Optional[MotionVector]:
        """최근 N프레임 기반 이동 벡터 계산."""
        if len(self.positions) < 2:
            return None

        # 최근 N프레임의 평균 이동량
        n = min(lookback_frames, len(self.positions) - 1)
        if n < 1:
            return None

        total_dx = 0.0
        total_dy = 0.0

        positions_list = list(self.positions)
        for i in range(1, n + 1):
            prev = positions_list[-(i + 1)]
            curr = positions_list[-i]
            total_dx += curr[0] - prev[0]
            total_dy += curr[1] - prev[1]

        return MotionVector(dx=total_dx / n, dy=total_dy / n)

    @property
    def current_position(self) -> Optional[Tuple[float, float]]:
        """현재 위치."""
        if self.positions:
            return self.positions[-1]
        return None


@dataclass
class MotionCorrelationResult:
    """움직임 상관관계 분석 결과."""
    product_detection: YOLODetection
    motion_correlation: float  # -1.0 ~ 1.0 (코사인 유사도)
    magnitude_similarity: float  # 0.0 ~ 1.0 (크기 유사도)
    motion_bonus: float  # 0.0 ~ 0.3 (최종 보너스)
    hand_velocity: Optional[MotionVector] = None
    product_velocity: Optional[MotionVector] = None

    @property
    def is_moving_together(self) -> bool:
        """손과 함께 움직이는지."""
        return self.motion_correlation > 0.7 and self.magnitude_similarity > 0.5


class MotionCorrelationFilter:
    """
    움직임 상관관계 필터.

    연속 프레임에서 손과 상품의 움직임을 추적하고,
    유사한 움직임 패턴을 보이는 상품에 가산점을 부여.

    Attributes:
        max_motion_bonus: 최대 움직임 보너스 (기본값 0.3)
        min_correlation: 보너스 부여 최소 상관관계 (기본값 0.5)
        lookback_frames: 이동 벡터 계산에 사용할 프레임 수 (기본값 3)
        hand_class_id: 손 클래스 ID (기본값 0)
    """

    HAND_CLASS_ID = 0

    def __init__(
        self,
        max_motion_bonus: float = 0.3,
        min_correlation: float = 0.5,
        lookback_frames: int = 3,
        hand_class_id: int = 0,
    ):
        """
        필터 초기화.

        Args:
            max_motion_bonus: 최대 움직임 보너스
            min_correlation: 보너스 부여 최소 상관관계
            lookback_frames: 이동 벡터 계산 프레임 수
            hand_class_id: 손 클래스 ID
        """
        self.max_motion_bonus = max_motion_bonus
        self.min_correlation = min_correlation
        self.lookback_frames = lookback_frames
        self.hand_class_id = hand_class_id

        # 추적 상태
        self._tracked_hands: Dict[int, TrackedObject] = {}  # hand_index -> TrackedObject
        self._tracked_products: Dict[int, TrackedObject] = {}  # class_id -> TrackedObject
        self._frame_count = 0
        self._last_update_time = 0.0

    def reset(self):
        """추적 상태 초기화."""
        self._tracked_hands.clear()
        self._tracked_products.clear()
        self._frame_count = 0
        self._last_update_time = 0.0
        logger.debug("Motion tracker reset")

    def update(self, detections: List[YOLODetection], timestamp: Optional[float] = None) -> List[MotionCorrelationResult]:
        """
        프레임 업데이트 및 상관관계 분석.

        Args:
            detections: 현재 프레임의 YOLO 감지 결과
            timestamp: 프레임 타임스탬프 (없으면 자동 생성)

        Returns:
            각 상품에 대한 MotionCorrelationResult 리스트
        """
        if timestamp is None:
            timestamp = time.time()

        self._frame_count += 1
        self._last_update_time = timestamp

        # 1. 손과 상품 분리
        hands = [d for d in detections if d.cls == self.hand_class_id]
        products = [d for d in detections if d.cls != self.hand_class_id]

        # 2. 손 위치 업데이트 (여러 손 지원)
        self._update_hands(hands, timestamp)

        # 3. 상품 위치 업데이트
        self._update_products(products, timestamp)

        # 4. 상관관계 분석 및 보너스 계산
        results = self._analyze_correlations(products)

        if results:
            moving_together = sum(1 for r in results if r.is_moving_together)
            logger.debug(
                f"Motion analysis: frame={self._frame_count}, "
                f"hands={len(hands)}, products={len(products)}, "
                f"moving_together={moving_together}"
            )

        return results

    def _update_hands(self, hands: List[YOLODetection], timestamp: float):
        """손 위치 업데이트."""
        # 간단한 방식: 인덱스 기반 매칭 (실제로는 IoU 기반 추적이 더 좋음)
        for i, hand in enumerate(hands):
            if i not in self._tracked_hands:
                self._tracked_hands[i] = TrackedObject(
                    class_id=self.hand_class_id,
                    class_name="hand",
                )

            self._tracked_hands[i].add_position(
                hand.center_x, hand.center_y, timestamp, hand.conf
            )

        # 오래된 손 추적 제거 (5프레임 이상 미감지)
        to_remove = []
        for idx, tracked in self._tracked_hands.items():
            if tracked.timestamps and timestamp - tracked.timestamps[-1] > 0.5:  # 0.5초
                to_remove.append(idx)

        for idx in to_remove:
            del self._tracked_hands[idx]

    def _update_products(self, products: List[YOLODetection], timestamp: float):
        """상품 위치 업데이트."""
        # 클래스 ID 기반 추적 (같은 클래스는 같은 객체로 간주)
        for product in products:
            if product.cls not in self._tracked_products:
                self._tracked_products[product.cls] = TrackedObject(
                    class_id=product.cls,
                    class_name=product.name,
                )

            self._tracked_products[product.cls].add_position(
                product.center_x, product.center_y, timestamp, product.conf
            )

    def _analyze_correlations(self, current_products: List[YOLODetection]) -> List[MotionCorrelationResult]:
        """상관관계 분석 및 보너스 계산."""
        results = []

        # 손 이동 벡터 계산 (가장 활발히 움직이는 손 사용)
        hand_velocity = self._get_primary_hand_velocity()

        for product in current_products:
            tracked = self._tracked_products.get(product.cls)

            if not tracked:
                # 추적 데이터 없음 → 보너스 없음
                results.append(MotionCorrelationResult(
                    product_detection=product,
                    motion_correlation=0.0,
                    magnitude_similarity=0.0,
                    motion_bonus=0.0,
                ))
                continue

            product_velocity = tracked.get_motion_vector(self.lookback_frames)

            # 이동 벡터가 없거나 손 데이터 없으면 보너스 없음
            if not hand_velocity or not product_velocity:
                results.append(MotionCorrelationResult(
                    product_detection=product,
                    motion_correlation=0.0,
                    magnitude_similarity=0.0,
                    motion_bonus=0.0,
                    hand_velocity=hand_velocity,
                    product_velocity=product_velocity,
                ))
                continue

            # 둘 다 의미 있는 움직임이 있어야 분석
            if not hand_velocity.is_significant or not product_velocity.is_significant:
                results.append(MotionCorrelationResult(
                    product_detection=product,
                    motion_correlation=0.0,
                    magnitude_similarity=0.0,
                    motion_bonus=0.0,
                    hand_velocity=hand_velocity,
                    product_velocity=product_velocity,
                ))
                continue

            # 상관관계 계산
            correlation = hand_velocity.cosine_similarity(product_velocity)
            mag_similarity = hand_velocity.magnitude_similarity(product_velocity)

            # 보너스 계산
            # correlation이 min_correlation 이상이고, magnitude도 유사해야 보너스
            motion_bonus = 0.0
            if correlation >= self.min_correlation and mag_similarity >= 0.3:
                # 보너스 = 상관관계 * 크기유사도 * 최대보너스
                motion_bonus = correlation * mag_similarity * self.max_motion_bonus
                motion_bonus = max(0.0, min(motion_bonus, self.max_motion_bonus))

            results.append(MotionCorrelationResult(
                product_detection=product,
                motion_correlation=correlation,
                magnitude_similarity=mag_similarity,
                motion_bonus=motion_bonus,
                hand_velocity=hand_velocity,
                product_velocity=product_velocity,
            ))

            if motion_bonus > 0:
                logger.info(
                    f"Motion bonus for {product.name}: "
                    f"correlation={correlation:.3f}, mag_sim={mag_similarity:.3f}, "
                    f"bonus={motion_bonus:.3f}"
                )

        return results

    def _get_primary_hand_velocity(self) -> Optional[MotionVector]:
        """
        주요 손의 이동 벡터 반환.

        여러 손이 있으면 가장 크게 움직이는 손 선택.
        """
        if not self._tracked_hands:
            return None

        best_velocity = None
        best_magnitude = 0.0

        for tracked in self._tracked_hands.values():
            velocity = tracked.get_motion_vector(self.lookback_frames)
            if velocity and velocity.magnitude > best_magnitude:
                best_velocity = velocity
                best_magnitude = velocity.magnitude

        return best_velocity

    def get_motion_bonus_map(self, detections: List[YOLODetection]) -> Dict[int, float]:
        """
        Detection 리스트에 대한 motion bonus 맵 반환.

        Args:
            detections: YOLO 감지 결과

        Returns:
            {class_id: motion_bonus} 딕셔너리
        """
        results = self.update(detections)
        return {r.product_detection.cls: r.motion_bonus for r in results}

    @property
    def frame_count(self) -> int:
        """처리된 프레임 수."""
        return self._frame_count

    @property
    def has_enough_frames(self) -> bool:
        """충분한 프레임이 축적되었는지 (최소 3프레임)."""
        return self._frame_count >= 3


# 싱글톤 인스턴스 (세션 간 상태 유지용)
_motion_filter_instance: Optional[MotionCorrelationFilter] = None


def get_motion_filter() -> MotionCorrelationFilter:
    """Motion Filter 싱글톤 인스턴스 반환."""
    global _motion_filter_instance
    if _motion_filter_instance is None:
        _motion_filter_instance = MotionCorrelationFilter()
    return _motion_filter_instance


def reset_motion_filter():
    """Motion Filter 상태 초기화."""
    global _motion_filter_instance
    if _motion_filter_instance:
        _motion_filter_instance.reset()
