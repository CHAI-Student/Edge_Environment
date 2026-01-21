"""
Vision Pipeline Tests.

YOLO 추론, Hand Filter, Top-5 추출, Multi-View Ensemble 테스트.
"""

import pytest
import numpy as np

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vision.hand_filter import HandProximityFilter, Detection, FilteredResult
from vision.top5_extractor import Top5Extractor, Candidate, Top5Result
from vision.multi_view_ensemble import MultiViewEnsemble, EnsembleCandidate


class TestHandProximityFilter:
    """Hand Proximity Filter 테스트."""

    def test_filter_with_hand_and_products(self):
        """손과 상품이 모두 있는 경우."""
        filter = HandProximityFilter(max_distance=150.0)

        detections = [
            Detection(class_id=0, name="hand", confidence=0.95,
                     bbox=(100, 100, 150, 150)),  # 손
            Detection(class_id=1, name="chickenmayo_rice", confidence=0.85,
                     bbox=(120, 120, 180, 180)),  # 가까운 상품
            Detection(class_id=2, name="samdasoo", confidence=0.75,
                     bbox=(400, 400, 450, 450)),  # 먼 상품
        ]

        result = filter.filter(detections)

        assert isinstance(result, FilteredResult)
        assert result.hand_detected
        assert len(result.products) >= 1
        # 가까운 상품만 포함되어야 함
        product_names = [p.name for p in result.products]
        assert "chickenmayo_rice" in product_names

    def test_filter_without_hand(self):
        """손이 없는 경우."""
        filter = HandProximityFilter()

        detections = [
            Detection(class_id=1, name="chickenmayo_rice", confidence=0.85,
                     bbox=(100, 100, 150, 150)),
            Detection(class_id=2, name="samdasoo", confidence=0.75,
                     bbox=(200, 200, 250, 250)),
        ]

        result = filter.filter(detections)

        assert not result.hand_detected
        # 손이 없으면 모든 상품 반환 또는 빈 리스트
        # 구현에 따라 다름

    def test_filter_empty_detections(self):
        """빈 감지 리스트."""
        filter = HandProximityFilter()

        result = filter.filter([])

        assert not result.hand_detected
        assert len(result.products) == 0

    def test_distance_calculation(self):
        """거리 계산 정확성."""
        filter = HandProximityFilter(max_distance=100.0)

        # 손 중심: (125, 125)
        hand = Detection(class_id=0, name="hand", confidence=0.9,
                        bbox=(100, 100, 150, 150))

        # 상품 중심: (175, 175) - 거리 약 70.7px
        near_product = Detection(class_id=1, name="near", confidence=0.8,
                                bbox=(150, 150, 200, 200))

        # 상품 중심: (325, 325) - 거리 약 283px
        far_product = Detection(class_id=2, name="far", confidence=0.8,
                               bbox=(300, 300, 350, 350))

        result = filter.filter([hand, near_product, far_product])

        assert result.hand_detected
        product_names = [p.name for p in result.products]
        assert "near" in product_names
        assert "far" not in product_names


class TestTop5Extractor:
    """Top-5 추출기 테스트."""

    def test_extract_top_5(self):
        """상위 5개 추출."""
        extractor = Top5Extractor(top_k=5)

        products = [
            Detection(class_id=1, name="product1", confidence=0.9, bbox=(0,0,10,10)),
            Detection(class_id=2, name="product2", confidence=0.8, bbox=(0,0,10,10)),
            Detection(class_id=3, name="product3", confidence=0.7, bbox=(0,0,10,10)),
            Detection(class_id=4, name="product4", confidence=0.6, bbox=(0,0,10,10)),
            Detection(class_id=5, name="product5", confidence=0.5, bbox=(0,0,10,10)),
            Detection(class_id=6, name="product6", confidence=0.4, bbox=(0,0,10,10)),
            Detection(class_id=7, name="product7", confidence=0.3, bbox=(0,0,10,10)),
        ]

        result = extractor.extract(products)

        assert isinstance(result, Top5Result)
        assert len(result.candidates) == 5
        # confidence 순으로 정렬되어야 함
        confidences = [c.conf for c in result.candidates]
        assert confidences == sorted(confidences, reverse=True)

    def test_extract_less_than_5(self):
        """5개 미만일 때."""
        extractor = Top5Extractor(top_k=5)

        products = [
            Detection(class_id=1, name="product1", confidence=0.9, bbox=(0,0,10,10)),
            Detection(class_id=2, name="product2", confidence=0.8, bbox=(0,0,10,10)),
        ]

        result = extractor.extract(products)

        assert len(result.candidates) == 2

    def test_extract_empty(self):
        """빈 리스트."""
        extractor = Top5Extractor()

        result = extractor.extract([])

        assert len(result.candidates) == 0

    def test_custom_top_k(self):
        """커스텀 top_k 값."""
        extractor = Top5Extractor(top_k=3)

        products = [
            Detection(class_id=i, name=f"product{i}", confidence=0.9-i*0.1, bbox=(0,0,10,10))
            for i in range(10)
        ]

        result = extractor.extract(products)

        assert len(result.candidates) == 3


class TestMultiViewEnsemble:
    """Multi-View Ensemble 테스트."""

    def test_ensemble_consensus(self):
        """양쪽 뷰에서 공통 감지된 상품."""
        ensemble = MultiViewEnsemble(
            top_weight=0.4,
            side_weight=0.6,
            common_class_bonus=0.2
        )

        top_candidates = [
            Candidate(class_id=1, name="chickenmayo", conf=0.85),
            Candidate(class_id=2, name="hotbar", conf=0.70),
        ]

        side_candidates = [
            Candidate(class_id=1, name="chickenmayo", conf=0.90),
            Candidate(class_id=3, name="samdasoo", conf=0.75),
        ]

        result = ensemble.ensemble(top_candidates, side_candidates)

        assert len(result) > 0
        # chickenmayo가 양쪽에서 감지되어 최상위여야 함
        assert result[0].name == "chickenmayo"
        assert result[0].source == "consensus"

    def test_ensemble_single_view_only(self):
        """한쪽 뷰에서만 감지된 상품."""
        ensemble = MultiViewEnsemble()

        top_candidates = [
            Candidate(class_id=1, name="product_top_only", conf=0.85),
        ]

        side_candidates = [
            Candidate(class_id=2, name="product_side_only", conf=0.90),
        ]

        result = ensemble.ensemble(top_candidates, side_candidates)

        sources = [r.source for r in result]
        assert "top_only" in sources or "side_only" in sources

    def test_ensemble_empty_inputs(self):
        """빈 입력."""
        ensemble = MultiViewEnsemble()

        result = ensemble.ensemble([], [])

        assert len(result) == 0

    def test_weighted_confidence(self):
        """가중 confidence 계산."""
        ensemble = MultiViewEnsemble(
            top_weight=0.4,
            side_weight=0.6,
            common_class_bonus=0.0  # 보너스 없이 테스트
        )

        top_candidates = [
            Candidate(class_id=1, name="product", conf=0.80),
        ]

        side_candidates = [
            Candidate(class_id=1, name="product", conf=0.90),
        ]

        result = ensemble.ensemble(top_candidates, side_candidates)

        # 가중 평균: 0.4 * 0.80 + 0.6 * 0.90 = 0.32 + 0.54 = 0.86
        expected = 0.86
        assert abs(result[0].combined_confidence - expected) < 0.01


class TestVisionIntegration:
    """Vision 파이프라인 통합 테스트."""

    def test_full_pipeline(self, sample_frame):
        """전체 파이프라인 (Mock YOLO)."""
        # YOLO 모델 없이 테스트
        # 실제 구현에서는 mock을 사용

        hand_filter = HandProximityFilter()
        top5_extractor = Top5Extractor()
        ensemble = MultiViewEnsemble()

        # Mock detections
        mock_detections = [
            Detection(class_id=0, name="hand", confidence=0.95,
                     bbox=(100, 100, 150, 150)),
            Detection(class_id=1, name="chickenmayo", confidence=0.88,
                     bbox=(120, 120, 180, 180)),
            Detection(class_id=2, name="hotbar", confidence=0.72,
                     bbox=(130, 130, 190, 190)),
        ]

        # Step 1: Hand filter
        filtered = hand_filter.filter(mock_detections)
        assert filtered.hand_detected

        # Step 2: Top-5 extract
        top5_result = top5_extractor.extract(filtered.products)
        assert len(top5_result.candidates) > 0

        # Step 3: Ensemble (single view in this case)
        # 실제로는 Top + Side 두 뷰를 앙상블
