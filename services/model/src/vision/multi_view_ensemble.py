"""
Multi-View Ensemble.

Top + Side 카메라 결과를 앙상블하여 최종 후보군 도출.

전략:
- 양쪽에서 공통으로 감지된 클래스에 보너스 부여
- 가중 평균으로 combined_confidence 계산
- 손과 함께 움직이는 상품에 motion_bonus 부여
"""

from typing import List, Dict, Optional
import logging

from .yolo_wrapper import YOLODetection
from .top5_extractor import Top5Extractor
from .motion_correlation_filter import MotionCorrelationFilter, get_motion_filter
from ..engine.models import EnsembleResult
from ..config import config

logger = logging.getLogger(__name__)


class MultiViewEnsemble:
    """
    Multi-View Ensemble.

    Top + Side 카메라에서 감지된 결과를 앙상블.
    손과 함께 움직이는 상품에 motion_bonus 추가 부여.
    """

    def __init__(
        self,
        top_weight: float = None,
        side_weight: float = None,
        common_class_bonus: float = None,
        max_motion_bonus: float = None,
        top_k: int = None,
        use_motion_tracking: bool = True,
    ):
        """
        앙상블 초기화.

        Args:
            top_weight: Top 카메라 가중치
            side_weight: Side 카메라 가중치
            common_class_bonus: 공통 클래스 보너스
            max_motion_bonus: 최대 움직임 보너스 (기본값 0.3)
            top_k: 최종 반환할 후보 수
            use_motion_tracking: 움직임 추적 사용 여부
        """
        self.top_weight = top_weight or config.top_weight
        self.side_weight = side_weight or config.side_weight
        self.common_class_bonus = common_class_bonus or config.common_class_bonus
        self.max_motion_bonus = max_motion_bonus or getattr(config, 'max_motion_bonus', 0.3)
        self.top_k = top_k or config.top_k
        self.use_motion_tracking = use_motion_tracking
        self.extractor = Top5Extractor()

        # Motion Correlation Filter
        self._motion_filter: Optional[MotionCorrelationFilter] = None
        if self.use_motion_tracking:
            self._motion_filter = get_motion_filter()

    def ensemble(
        self,
        top_candidates: List[YOLODetection],
        side_candidates: List[YOLODetection],
        motion_bonus_map: Optional[Dict[int, float]] = None,
    ) -> List[EnsembleResult]:
        """
        Multi-View Ensemble (Top + Side 카메라).

        양쪽에서 공통으로 감지된 클래스에 보너스 부여.
        손과 함께 움직이는 상품에 motion_bonus 추가 부여.

        Args:
            top_candidates: Top 카메라 후보군
            side_candidates: Side 카메라 후보군
            motion_bonus_map: {class_id: motion_bonus} 딕셔너리 (외부에서 전달)

        Returns:
            EnsembleResult 리스트 (combined_confidence 내림차순)
        """
        motion_bonus_map = motion_bonus_map or {}

        # 클래스별 정보 집계
        class_scores: Dict[int, Dict] = {}

        # Top 카메라
        for det in top_candidates:
            if det.cls not in class_scores:
                class_scores[det.cls] = {
                    "name": det.name,
                    "top_conf": 0.0,
                    "side_conf": 0.0,
                }
            class_scores[det.cls]["top_conf"] = max(
                class_scores[det.cls]["top_conf"],
                det.conf,
            )

        # Side 카메라
        for det in side_candidates:
            if det.cls not in class_scores:
                class_scores[det.cls] = {
                    "name": det.name,
                    "top_conf": 0.0,
                    "side_conf": 0.0,
                }
            class_scores[det.cls]["side_conf"] = max(
                class_scores[det.cls]["side_conf"],
                det.conf,
            )

        # 앙상블 계산
        results = []

        for cls_id, scores in class_scores.items():
            if cls_id == 0:  # 손 제외
                continue

            top_conf = scores["top_conf"]
            side_conf = scores["side_conf"]

            # 양쪽에서 감지됨 (consensus)
            vote_count = (1 if top_conf > 0 else 0) + (1 if side_conf > 0 else 0)

            # 가중 평균 + 공통 클래스 보너스
            if top_conf > 0 and side_conf > 0:
                combined = (
                    top_conf * self.top_weight +
                    side_conf * self.side_weight +
                    self.common_class_bonus
                )
            elif top_conf > 0:
                combined = top_conf * self.top_weight
            else:
                combined = side_conf * self.side_weight

            # Motion Bonus 추가 (손과 함께 움직이는 상품)
            motion_bonus = motion_bonus_map.get(cls_id, 0.0)
            if motion_bonus > 0:
                combined += motion_bonus
                logger.info(
                    f"Motion bonus applied to {scores['name']}: "
                    f"+{motion_bonus:.3f} (total: {combined:.3f})"
                )

            combined = min(combined, 1.0)

            result = EnsembleResult(
                class_id=cls_id,
                class_name=scores["name"],
                top_confidence=top_conf,
                side_confidence=side_conf,
                combined_confidence=combined,
                vote_count=vote_count,
            )
            results.append(result)

        # combined_confidence 내림차순 정렬
        results.sort(key=lambda r: r.combined_confidence, reverse=True)

        motion_applied = sum(1 for cls_id in class_scores if motion_bonus_map.get(cls_id, 0) > 0)
        logger.info(
            f"Ensemble: {len(results)} classes, "
            f"{sum(1 for r in results if r.vote_count == 2)} consensus, "
            f"{motion_applied} with motion bonus"
        )

        return results[:self.top_k]

    def update_motion_tracking(
        self,
        all_detections: List[YOLODetection],
        timestamp: Optional[float] = None,
    ) -> Dict[int, float]:
        """
        Motion Tracking 업데이트.

        연속 프레임에서 호출하여 손-상품 움직임 상관관계를 추적.

        Args:
            all_detections: 현재 프레임의 모든 YOLO 감지 결과
            timestamp: 프레임 타임스탬프

        Returns:
            {class_id: motion_bonus} 딕셔너리
        """
        if not self.use_motion_tracking or not self._motion_filter:
            return {}

        return self._motion_filter.get_motion_bonus_map(all_detections)

    def reset_motion_tracking(self):
        """Motion Tracking 상태 초기화."""
        if self._motion_filter:
            self._motion_filter.reset()

    def process_dual_camera(
        self,
        top_detections: List[YOLODetection],
        side_detections: List[YOLODetection],
        motion_bonus_map: Optional[Dict[int, float]] = None,
    ) -> List[EnsembleResult]:
        """
        Dual Camera 전체 파이프라인.

        1. 각 카메라에서 Top-K 추출
        2. Multi-View Ensemble (with motion bonus)

        Args:
            top_detections: Top 카메라 YOLO 결과
            side_detections: Side 카메라 YOLO 결과
            motion_bonus_map: 외부에서 전달된 motion bonus 맵

        Returns:
            앙상블된 EnsembleResult 리스트
        """
        # 각 카메라에서 추출
        top_result = self.extractor.extract(top_detections)
        side_result = self.extractor.extract(side_detections)

        # 앙상블
        return self.ensemble(
            top_candidates=top_result.candidates,
            side_candidates=side_result.candidates,
            motion_bonus_map=motion_bonus_map,
        )

    def process_frame_sequence(
        self,
        frame_detections: List[List[YOLODetection]],
        timestamps: Optional[List[float]] = None,
    ) -> List[EnsembleResult]:
        """
        연속 프레임 시퀀스 처리 (Motion Tracking 포함).

        여러 프레임의 detection을 순차적으로 처리하여
        motion correlation을 분석하고 최종 ensemble 결과 반환.

        Args:
            frame_detections: 프레임별 YOLO 감지 결과 리스트
            timestamps: 프레임별 타임스탬프 리스트

        Returns:
            최종 EnsembleResult 리스트
        """
        if not frame_detections:
            return []

        # Motion Filter 초기화
        self.reset_motion_tracking()

        motion_bonus_map = {}

        # 각 프레임 순차 처리
        for i, detections in enumerate(frame_detections):
            timestamp = timestamps[i] if timestamps else None

            # Motion Tracking 업데이트
            if self.use_motion_tracking and self._motion_filter:
                motion_bonus_map = self._motion_filter.get_motion_bonus_map(detections)

        # 마지막 프레임으로 최종 앙상블
        last_detections = frame_detections[-1]
        hands = [d for d in last_detections if d.cls == 0]
        products = [d for d in last_detections if d.cls != 0]

        # Top/Side 분리가 필요한 경우 외부에서 처리해야 함
        # 여기서는 모든 detection을 side로 간주
        return self.ensemble(
            top_candidates=[],
            side_candidates=products,
            motion_bonus_map=motion_bonus_map,
        )
