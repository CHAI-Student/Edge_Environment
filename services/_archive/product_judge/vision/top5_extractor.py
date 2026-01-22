"""
Top-5 Candidate Extractor.

YOLO 감지 결과에서 Top-5 후보군 추출.

파이프라인:
1. YOLO 감지 (conf=0.01, 매우 낮은 threshold)
2. 손/상품 분리
3. 손 근접 필터링
4. Top-5 confidence 추출
5. (옵션) Multi-View Ensemble

사용 예시:
    extractor = Top5Extractor()
    candidates = extractor.extract(detections)
    ensemble_results = extractor.ensemble(top_candidates, side_candidates)
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import logging

from .yolo_wrapper import YOLODetection
from .hand_filter import HandProximityFilter
from ..engine.models import EnsembleResult

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """추출 결과."""
    candidates: List[YOLODetection]  # Top-K 후보군
    hands: List[YOLODetection]       # 감지된 손
    total_detected: int              # 총 감지 수
    filtered_count: int              # 필터 후 수


class Top5Extractor:
    """
    Top-5 후보군 추출기.

    손 근접 필터링 후 confidence 상위 5개 추출.

    Attributes:
        hand_filter: 손 근접 필터
        top_k: 추출할 후보 수 (기본값 5)
    """

    def __init__(
        self,
        max_distance_px: float = 150.0,
        top_k: int = 5,
        hand_class_id: int = 0,
    ):
        """
        추출기 초기화.

        Args:
            max_distance_px: 손-상품 최대 거리
            top_k: 추출할 후보 수
            hand_class_id: 손 클래스 ID
        """
        self.hand_filter = HandProximityFilter(
            max_distance_px=max_distance_px,
            hand_class_id=hand_class_id,
        )
        self.top_k = top_k

    def extract(
        self,
        detections: List[YOLODetection],
    ) -> ExtractionResult:
        """
        Top-K 후보군 추출.

        Args:
            detections: YOLO 감지 결과

        Returns:
            ExtractionResult
        """
        # 손 근접 필터링
        filter_result = self.hand_filter.filter(detections)

        # confidence 정렬 후 Top-K 추출
        sorted_products = sorted(
            filter_result.filtered_products,
            key=lambda d: d.conf,
            reverse=True,
        )
        candidates = sorted_products[:self.top_k]

        logger.info(
            f"Extracted Top-{len(candidates)} from "
            f"{filter_result.filtered_count if hasattr(filter_result, 'filtered_count') else len(filter_result.filtered_products)} filtered "
            f"({len(filter_result.all_products)} total products)"
        )

        return ExtractionResult(
            candidates=candidates,
            hands=filter_result.hands,
            total_detected=len(filter_result.all_products),
            filtered_count=len(filter_result.filtered_products),
        )

    def extract_from_raw(
        self,
        detection_data: List[dict],
    ) -> ExtractionResult:
        """
        딕셔너리 데이터에서 추출 (테스트/API용).

        Args:
            detection_data: [{"xyxy": [...], "conf": ..., "cls": ..., "name": ...}, ...]

        Returns:
            ExtractionResult
        """
        from .yolo_wrapper import YOLOWrapper
        detections = YOLOWrapper.parse_detection_list(detection_data)
        return self.extract(detections)

    def ensemble(
        self,
        top_candidates: List[YOLODetection],
        side_candidates: List[YOLODetection],
        top_weight: float = 0.5,
        side_weight: float = 0.5,
        common_class_bonus: float = 0.2,
    ) -> List[EnsembleResult]:
        """
        Multi-View Ensemble (Top + Side 카메라).

        양쪽에서 공통으로 감지된 클래스에 보너스 부여.

        Args:
            top_candidates: Top 카메라 후보군
            side_candidates: Side 카메라 후보군
            top_weight: Top 카메라 가중치
            side_weight: Side 카메라 가중치
            common_class_bonus: 공통 클래스 보너스

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
                    top_conf * top_weight +
                    side_conf * side_weight +
                    common_class_bonus
                )
            elif top_conf > 0:
                combined = top_conf * top_weight
            else:
                combined = side_conf * side_weight

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
        top_result = self.extract(top_detections)
        side_result = self.extract(side_detections)

        # 앙상블
        return self.ensemble(
            top_candidates=top_result.candidates,
            side_candidates=side_result.candidates,
        )

    def process_single_camera(
        self,
        detections: List[YOLODetection],
    ) -> List[EnsembleResult]:
        """
        단일 카메라 처리 (앙상블 없음).

        Top-K 추출 후 EnsembleResult 형식으로 변환.

        Args:
            detections: YOLO 감지 결과

        Returns:
            EnsembleResult 리스트
        """
        result = self.extract(detections)

        ensemble_results = []
        for det in result.candidates:
            if det.is_hand:
                continue

            er = EnsembleResult(
                class_id=det.cls,
                class_name=det.name,
                top_confidence=det.conf,
                side_confidence=0.0,
                combined_confidence=det.conf,
                vote_count=1,
            )
            ensemble_results.append(er)

        return ensemble_results
