"""
Multi-View Ensemble.

Top + Side 카메라 결과를 앙상블하여 최종 후보군 도출.

전략:
- 양쪽에서 공통으로 감지된 클래스에 보너스 부여
- 가중 평균으로 combined_confidence 계산
"""

from typing import List, Dict
import logging

from .yolo_wrapper import YOLODetection
from .top5_extractor import Top5Extractor
from ..engine.models import EnsembleResult
from ..config import config

logger = logging.getLogger(__name__)


class MultiViewEnsemble:
    """
    Multi-View Ensemble.

    Top + Side 카메라에서 감지된 결과를 앙상블.
    """

    def __init__(
        self,
        top_weight: float = None,
        side_weight: float = None,
        common_class_bonus: float = None,
        top_k: int = None,
    ):
        """
        앙상블 초기화.

        Args:
            top_weight: Top 카메라 가중치
            side_weight: Side 카메라 가중치
            common_class_bonus: 공통 클래스 보너스
            top_k: 최종 반환할 후보 수
        """
        self.top_weight = top_weight or config.top_weight
        self.side_weight = side_weight or config.side_weight
        self.common_class_bonus = common_class_bonus or config.common_class_bonus
        self.top_k = top_k or config.top_k
        self.extractor = Top5Extractor()

    def ensemble(
        self,
        top_candidates: List[YOLODetection],
        side_candidates: List[YOLODetection],
    ) -> List[EnsembleResult]:
        """
        Multi-View Ensemble (Top + Side 카메라).

        양쪽에서 공통으로 감지된 클래스에 보너스 부여.

        Args:
            top_candidates: Top 카메라 후보군
            side_candidates: Side 카메라 후보군

        Returns:
            EnsembleResult 리스트 (combined_confidence 내림차순)
        """
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

            # 가중 평균 + 보너스
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

        logger.info(
            f"Ensemble: {len(results)} classes, "
            f"{sum(1 for r in results if r.vote_count == 2)} consensus"
        )

        return results[:self.top_k]

    def process_dual_camera(
        self,
        top_detections: List[YOLODetection],
        side_detections: List[YOLODetection],
    ) -> List[EnsembleResult]:
        """
        Dual Camera 전체 파이프라인.

        1. 각 카메라에서 Top-K 추출
        2. Multi-View Ensemble

        Args:
            top_detections: Top 카메라 YOLO 결과
            side_detections: Side 카메라 YOLO 결과

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
        )
