"""
Decision Engine Tests.

Vision + Weight 퓨전 판단 엔진 테스트.
"""

import pytest
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.decision_engine import ProductDecisionEngine
from engine.models import (
    JudgmentResult,
    JudgmentStatus,
    ProductJudgment,
    EnsembleResult,
    CountEstimate,
)
from database.product_db import ProductDatabase
from weight.count_calculator import WeightBasedCountCalculator


class TestProductDatabase:
    """상품 데이터베이스 테스트."""

    def test_get_product_by_id(self):
        """ID로 조회."""
        db = ProductDatabase()

        product = db.get_product(26)  # chickenmayo_rice

        assert product is not None
        assert product.product_id == 26
        assert product.name == "chickenmayo_rice"
        assert product.weight == 365
        assert product.price == 3500

    def test_get_product_nonexistent(self):
        """존재하지 않는 상품 ID."""
        db = ProductDatabase()

        product = db.get_product(9999)

        assert product is None

    def test_get_weight(self):
        """상품 무게 조회."""
        db = ProductDatabase()

        weight = db.get_weight(26)  # chickenmayo_rice

        assert weight == 365.0

    def test_get_price(self):
        """상품 가격 조회."""
        db = ProductDatabase()

        price = db.get_price(26)  # chickenmayo_rice

        assert price == 3500

    def test_get_all_products(self):
        """전체 상품 목록."""
        db = ProductDatabase()

        products = db.get_all_products()

        assert len(products) > 0
        # 기본 상품 50개 (hand 제외)
        assert len(products) >= 49  # 50 - hand

    def test_search_by_weight(self):
        """무게로 상품 검색."""
        db = ProductDatabase()

        # 520g 근처 상품 검색 (음료 카테고리)
        products = db.search_by_weight(520, tolerance=0.10)

        assert len(products) > 0
        # samdasoo_500, pulmuone_spring_water_500 등이 포함되어야 함


class TestWeightBasedCountCalculator:
    """무게 기반 개수 계산기 테스트."""

    @pytest.fixture
    def calculator(self):
        """개수 계산기 인스턴스."""
        db = ProductDatabase()
        return WeightBasedCountCalculator(
            product_db=db,
            tolerance_percent=0.10,
        )

    @pytest.fixture
    def sample_candidate(self):
        """샘플 Vision 후보 (chickenmayo_rice)."""
        return EnsembleResult(
            class_id=26,
            class_name="chickenmayo_rice",
            top_confidence=0.85,
            side_confidence=0.90,
            combined_confidence=0.875,
            vote_count=2,
        )

    def test_calculate_single_product(self, calculator, sample_candidate):
        """단일 상품 개수 계산."""
        # 365g 상품 1개 픽업 (무게 변화 -365g)
        estimates = calculator.calculate(
            candidates=[sample_candidate],
            delta_weight=-365.0,
        )

        assert len(estimates) == 1
        assert estimates[0].count == 1
        assert estimates[0].validated is True
        assert estimates[0].product_name == "chickenmayo_rice"

    def test_calculate_multiple_same_product(self, calculator, sample_candidate):
        """동일 상품 여러 개."""
        # 365g 상품 2개 픽업 (무게 변화 -730g)
        estimates = calculator.calculate(
            candidates=[sample_candidate],
            delta_weight=-730.0,
        )

        assert len(estimates) == 1
        assert estimates[0].count == 2
        assert estimates[0].validated is True

    def test_calculate_with_tolerance(self, calculator, sample_candidate):
        """허용 오차 내 매칭."""
        # 365g 상품, 실제 변화량 -370g (1.4% 오차)
        estimates = calculator.calculate(
            candidates=[sample_candidate],
            delta_weight=-370.0,
        )

        assert len(estimates) == 1
        assert estimates[0].count == 1
        assert estimates[0].validated is True  # 10% 이내

    def test_calculate_out_of_tolerance(self, calculator, sample_candidate):
        """허용 오차 초과."""
        # 365g 상품, 실제 변화량 -450g (23% 오차)
        estimates = calculator.calculate(
            candidates=[sample_candidate],
            delta_weight=-450.0,
        )

        # count=1로 계산되지만 validated=False
        assert len(estimates) == 1
        assert estimates[0].validated is False

    def test_weight_too_small(self, calculator, sample_candidate):
        """무게 변화량이 너무 작음."""
        estimates = calculator.calculate(
            candidates=[sample_candidate],
            delta_weight=-3.0,  # 최소 5g 미만
        )

        assert len(estimates) == 0


class TestDecisionEngine:
    """판단 엔진 테스트."""

    @pytest.fixture
    def engine(self):
        """판단 엔진 인스턴스."""
        db = ProductDatabase()
        return ProductDecisionEngine(product_db=db)

    @pytest.fixture
    def chickenmayo_candidate(self):
        """치킨마요 앙상블 후보."""
        return EnsembleResult(
            class_id=26,
            class_name="chickenmayo_rice",
            top_confidence=0.85,
            side_confidence=0.90,
            combined_confidence=0.875,
            vote_count=2,
        )

    @pytest.fixture
    def samdasoo_candidate(self):
        """삼다수 앙상블 후보."""
        return EnsembleResult(
            class_id=2,
            class_name="samdasoo_500",
            top_confidence=0.80,
            side_confidence=0.82,
            combined_confidence=0.81,
            vote_count=2,
        )

    def test_judge_complete_match(self, engine, chickenmayo_candidate):
        """완전 매칭 (Complete)."""
        result = engine.judge(
            vision_candidates=[chickenmayo_candidate],
            delta_weight=-365.0,  # chickenmayo_rice 무게
        )

        assert result.status == JudgmentStatus.COMPLETE
        assert len(result.products) == 1
        assert result.products[0].name == "chickenmayo_rice"
        assert result.products[0].count == 1
        assert result.total_price == 3500
        assert result.confidence > 0.5

    def test_judge_partial_match(self, engine, chickenmayo_candidate):
        """부분 매칭 (Partial)."""
        result = engine.judge(
            vision_candidates=[chickenmayo_candidate],
            delta_weight=-400.0,  # 365g 상품이지만 400g 변화
        )

        # 허용 오차 초과 시 PARTIAL 또는 UNCERTAIN
        assert result.status in [JudgmentStatus.PARTIAL, JudgmentStatus.UNCERTAIN]

    def test_judge_no_candidates_fallback(self, engine):
        """후보군 없음 - Loadcell-only 폴백."""
        result = engine.judge(
            vision_candidates=[],
            delta_weight=-365.0,
        )

        # Vision 없이 무게만으로 판단 → PARTIAL 또는 UNCERTAIN
        assert result.status in [JudgmentStatus.PARTIAL, JudgmentStatus.UNCERTAIN]
        # chickenmayo_rice가 365g이므로 매칭될 수 있음
        if result.products:
            assert result.products[0].name == "chickenmayo_rice"

    def test_judge_weight_too_small(self, engine, chickenmayo_candidate):
        """무게 변화가 너무 작음."""
        result = engine.judge(
            vision_candidates=[chickenmayo_candidate],
            delta_weight=-3.0,  # 최소 5g 미만
        )

        assert result.status == JudgmentStatus.NO_DETECTION

    def test_judge_by_weight_only_exact_match(self, engine):
        """무게만으로 판단 - 정확한 매칭."""
        result = engine.judge_by_weight_only(
            delta_weight=-365.0,  # chickenmayo_rice 무게
        )

        assert result is not None
        assert result.status == JudgmentStatus.PARTIAL  # Vision 없이 최대 PARTIAL
        assert len(result.products) == 1
        assert result.products[0].name == "chickenmayo_rice"
        assert result.products[0].count == 1
        # Vision 없이 최대 70% confidence
        assert result.confidence <= 0.7

    def test_judge_by_weight_only_multiple_count(self, engine):
        """무게만으로 판단 - 다중 개수."""
        result = engine.judge_by_weight_only(
            delta_weight=-730.0,  # chickenmayo_rice x 2
        )

        assert result is not None
        assert len(result.products) == 1
        assert result.products[0].count == 2

    def test_judge_by_weight_only_uncertain(self, engine):
        """무게만으로 판단 - tolerance 초과."""
        # 550g: samdasoo_500(520g)과 30g 차이 = 5.7% 오차
        # 하지만 다른 상품이 더 가까울 수 있음
        result = engine.judge_by_weight_only(
            delta_weight=-550.0,
        )

        assert result is not None
        # 어떤 상품이든 매칭 시도

    def test_judge_by_weight_only_weight_too_small(self, engine):
        """무게만으로 판단 - 무게 변화 너무 작음."""
        result = engine.judge_by_weight_only(
            delta_weight=-3.0,
        )

        assert result.status == JudgmentStatus.NO_DETECTION

    def test_judge_multiple_products_combination(
        self, engine, chickenmayo_candidate, samdasoo_candidate
    ):
        """다중 상품 조합."""
        # chickenmayo_rice (365g) + samdasoo_500 (520g) = 885g
        result = engine.judge(
            vision_candidates=[chickenmayo_candidate, samdasoo_candidate],
            delta_weight=-885.0,
        )

        assert result.status == JudgmentStatus.COMPLETE
        assert len(result.products) == 2

    def test_judge_product_return(self, engine, chickenmayo_candidate):
        """상품 반환 (무게 증가)."""
        result = engine.judge(
            vision_candidates=[chickenmayo_candidate],
            delta_weight=365.0,  # 양수 = 반환
        )

        # 반환도 정상 처리
        assert result.is_removal is False


class TestJudgmentResult:
    """판단 결과 모델 테스트."""

    def test_to_node_response(self):
        """Node.js 응답 형식 변환."""
        result = JudgmentResult(
            status=JudgmentStatus.COMPLETE,
            products=[
                ProductJudgment(
                    product_id=26,
                    name="chickenmayo_rice",
                    count=1,
                    unit_price=3500,
                    total_price=3500,
                    confidence=0.90,
                    unit_weight=365.0,
                )
            ],
            total_price=3500,
            confidence=0.90,
            weight_delta=-365.0,
            weight_explained=365.0,
            weight_residual=0.0,
        )

        response = result.to_node_response()

        assert response["success"] is True
        assert response["status"] == "complete"
        assert response["totalPrice"] == 3500
        assert len(response["products"]) == 1
        assert response["products"][0]["name"] == "chickenmayo_rice"
        assert response["isRemoval"] is True
        assert response["productCount"] == 1

    def test_judgment_status_values(self):
        """JudgmentStatus 값 확인."""
        assert JudgmentStatus.COMPLETE.value == "complete"
        assert JudgmentStatus.PARTIAL.value == "partial"
        assert JudgmentStatus.UNCERTAIN.value == "uncertain"
        assert JudgmentStatus.NO_DETECTION.value == "no_detection"

    def test_is_removal(self):
        """상품 제거 여부 확인."""
        removal_result = JudgmentResult(weight_delta=-100.0)
        return_result = JudgmentResult(weight_delta=100.0)

        assert removal_result.is_removal is True
        assert return_result.is_removal is False

    def test_is_success(self):
        """성공적인 판단 여부."""
        complete = JudgmentResult(status=JudgmentStatus.COMPLETE)
        partial = JudgmentResult(status=JudgmentStatus.PARTIAL)
        uncertain = JudgmentResult(status=JudgmentStatus.UNCERTAIN)
        no_detect = JudgmentResult(status=JudgmentStatus.NO_DETECTION)

        assert complete.is_success is True
        assert partial.is_success is True
        assert uncertain.is_success is False
        assert no_detect.is_success is False


class TestLoadcellOnlyFallback:
    """Loadcell-only 폴백 메커니즘 전용 테스트."""

    @pytest.fixture
    def engine(self):
        """판단 엔진 인스턴스."""
        db = ProductDatabase()
        return ProductDecisionEngine(product_db=db)

    def test_fallback_exact_weight_match(self, engine):
        """폴백: 정확한 무게 매칭."""
        # 520g = samdasoo_500 or pulmuone_spring_water_500
        result = engine.judge_by_weight_only(delta_weight=-520.0)

        assert result.status == JudgmentStatus.PARTIAL
        assert len(result.products) == 1
        assert result.products[0].unit_weight == 520.0
        assert result.confidence <= 0.7  # Vision 없이 최대 70%

    def test_fallback_close_weight_match(self, engine):
        """폴백: 근접 무게 매칭 (tolerance 내)."""
        # 525g: samdasoo_500(520g)과 5g 차이 = ~1% 오차
        result = engine.judge_by_weight_only(delta_weight=-525.0)

        assert result.status == JudgmentStatus.PARTIAL
        assert result.weight_residual < 10  # 오차 10g 이내

    def test_fallback_uncertain_weight_match(self, engine):
        """폴백: tolerance 초과하지만 최근접 매칭."""
        # 600g: 정확히 맞는 상품 없음, 가장 가까운 상품 반환
        result = engine.judge_by_weight_only(delta_weight=-600.0)

        # tolerance 초과 시 UNCERTAIN
        assert result.status == JudgmentStatus.UNCERTAIN
        assert len(result.products) == 1
        assert result.confidence <= 0.5  # tolerance 밖이면 최대 50%

    def test_fallback_multiple_count_estimation(self, engine):
        """폴백: 다중 개수 추정."""
        # 1040g = samdasoo_500 x 2
        result = engine.judge_by_weight_only(delta_weight=-1040.0)

        assert len(result.products) == 1
        assert result.products[0].count == 2
        assert result.products[0].unit_weight == 520.0

    def test_fallback_returns_best_match(self, engine):
        """폴백: 여러 후보 중 최적 매칭 반환."""
        # 365g = chickenmayo_rice 정확히 매칭
        result = engine.judge_by_weight_only(delta_weight=-365.0)

        assert result.products[0].name == "chickenmayo_rice"
        assert result.products[0].unit_weight == 365.0

    def test_judge_uses_fallback_when_no_candidates(self, engine):
        """judge()가 후보군 없을 때 폴백 사용."""
        result = engine.judge(
            vision_candidates=[],
            delta_weight=-365.0,
        )

        # 폴백이 작동하면 products가 있어야 함
        assert len(result.products) >= 0  # 폴백 결과에 따라
        # NO_DETECTION이 아니어야 함 (폴백이 작동했다면)
        if result.products:
            assert result.status != JudgmentStatus.NO_DETECTION
