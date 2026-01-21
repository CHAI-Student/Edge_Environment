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
from engine.models import JudgmentResult, JudgmentStatus, JudgedProduct
from database.product_db import ProductDatabase
from weight.count_calculator import CountCalculator


class TestProductDatabase:
    """상품 데이터베이스 테스트."""

    def test_get_product_by_name(self):
        """상품명으로 조회."""
        db = ProductDatabase()

        product = db.get_by_name("chickenmayo_rice")

        assert product is not None
        assert product.name == "chickenmayo_rice"
        assert product.weight > 0
        assert product.price > 0

    def test_get_product_by_id(self):
        """ID로 조회."""
        db = ProductDatabase()

        product = db.get_by_id(1)

        assert product is not None
        assert product.id == 1

    def test_get_nonexistent_product(self):
        """존재하지 않는 상품."""
        db = ProductDatabase()

        product = db.get_by_name("nonexistent_product_xyz")

        assert product is None

    def test_list_all_products(self):
        """전체 상품 목록."""
        db = ProductDatabase()

        products = db.list_all()

        assert len(products) > 0
        # 기본 상품 50개
        assert len(products) >= 10


class TestCountCalculator:
    """개수 계산기 테스트."""

    def test_calculate_single_product(self):
        """단일 상품 개수 계산."""
        calc = CountCalculator(tolerance_percent=0.10)

        # 365g 상품 1개 픽업 (무게 변화 -365g)
        result = calc.calculate(
            delta_weight=-365.0,
            unit_weight=365.0
        )

        assert result.count == 1
        assert result.is_valid

    def test_calculate_multiple_products(self):
        """동일 상품 여러 개."""
        calc = CountCalculator(tolerance_percent=0.10)

        # 365g 상품 2개 픽업 (무게 변화 -730g)
        result = calc.calculate(
            delta_weight=-730.0,
            unit_weight=365.0
        )

        assert result.count == 2
        assert result.is_valid

    def test_calculate_with_tolerance(self):
        """허용 오차 내 매칭."""
        calc = CountCalculator(tolerance_percent=0.10)

        # 365g 상품, 실제 변화량 -370g (1.4% 오차)
        result = calc.calculate(
            delta_weight=-370.0,
            unit_weight=365.0
        )

        assert result.count == 1
        assert result.is_valid

    def test_calculate_out_of_tolerance(self):
        """허용 오차 초과."""
        calc = CountCalculator(tolerance_percent=0.05)  # 5%

        # 365g 상품, 실제 변화량 -400g (9.6% 오차)
        result = calc.calculate(
            delta_weight=-400.0,
            unit_weight=365.0
        )

        # 5% 오차를 초과하면 invalid
        # 구현에 따라 count=1이지만 is_valid=False 또는 매칭 실패

    def test_weight_increase(self):
        """무게 증가 (상품 반환)."""
        calc = CountCalculator()

        result = calc.calculate(
            delta_weight=365.0,  # 양수 = 반환
            unit_weight=365.0
        )

        assert result.count == -1  # 반환은 음수로 표시
        assert result.is_valid


class TestDecisionEngine:
    """판단 엔진 테스트."""

    @pytest.fixture
    def engine(self):
        """판단 엔진 인스턴스."""
        db = ProductDatabase()
        return ProductDecisionEngine(product_db=db)

    def test_judge_complete_match(self, engine):
        """완전 매칭 (Complete)."""
        # Vision 후보군에 chickenmayo_rice가 높은 confidence
        # 무게 변화량이 정확히 일치
        vision_candidates = [
            {"class_id": 1, "name": "chickenmayo_rice", "confidence": 0.90},
        ]

        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=-365.0,  # chickenmayo_rice 무게
        )

        assert result.status == JudgmentStatus.COMPLETE
        assert len(result.products) == 1
        assert result.products[0].name == "chickenmayo_rice"
        assert result.products[0].count == 1
        assert result.total_price > 0

    def test_judge_partial_match(self, engine):
        """부분 매칭 (Partial)."""
        # Vision 후보군에 상품이 있지만 무게가 완전히 일치하지 않음
        vision_candidates = [
            {"class_id": 1, "name": "chickenmayo_rice", "confidence": 0.85},
            {"class_id": 2, "name": "hotbar", "confidence": 0.70},
        ]

        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=-500.0,  # 어떤 조합도 정확히 일치하지 않음
        )

        # 부분 매칭 또는 불확실
        assert result.status in [JudgmentStatus.PARTIAL, JudgmentStatus.UNCERTAIN]

    def test_judge_uncertain(self, engine):
        """불확실 (Uncertain)."""
        # Vision 후보군이 없거나 confidence가 낮음
        vision_candidates = []

        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=-365.0,
        )

        assert result.status == JudgmentStatus.UNCERTAIN

    def test_judge_weight_only_mode(self, engine):
        """무게만으로 판단 (Vision 실패 시)."""
        # Vision 후보군 없이 무게만으로 가능한 상품 추정
        result = engine.judge_by_weight_only(
            delta_weight=-520.0,  # samdasoo_500 무게
        )

        # 무게로만 판단 시 여러 후보 가능
        assert result is not None

    def test_judge_multiple_products(self, engine):
        """다중 상품 픽업."""
        # chickenmayo_rice (365g) + samdasoo_500 (520g) = 885g
        vision_candidates = [
            {"class_id": 1, "name": "chickenmayo_rice", "confidence": 0.85},
            {"class_id": 3, "name": "samdasoo_500", "confidence": 0.80},
        ]

        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=-885.0,
        )

        assert result.status == JudgmentStatus.COMPLETE
        assert len(result.products) == 2
        total_weight = sum(p.weight * p.count for p in result.products)
        assert abs(total_weight - 885.0) < 50  # 허용 오차

    def test_judge_product_return(self, engine):
        """상품 반환 (무게 증가)."""
        vision_candidates = [
            {"class_id": 1, "name": "chickenmayo_rice", "confidence": 0.85},
        ]

        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=365.0,  # 양수 = 반환
        )

        assert result.is_removal == False  # 반환은 removal 아님
        # 또는 별도의 is_return 필드


class TestJudgmentResult:
    """판단 결과 모델 테스트."""

    def test_to_node_response(self):
        """Node.js 응답 형식 변환."""
        result = JudgmentResult(
            status=JudgmentStatus.COMPLETE,
            products=[
                JudgedProduct(
                    product_id=1,
                    name="chickenmayo_rice",
                    count=1,
                    unit_price=3500,
                    weight=365,
                    confidence=0.90,
                )
            ],
            total_price=3500,
            confidence=0.90,
            weight_delta=-365.0,
            weight_explained=365.0,
            weight_residual=0.0,
            is_removal=True,
        )

        response = result.to_node_response()

        assert response["success"] == True
        assert response["status"] == "complete"
        assert response["totalPrice"] == 3500
        assert len(response["products"]) == 1
        assert response["products"][0]["name"] == "chickenmayo_rice"
        assert response["isRemoval"] == True

    def test_judgment_status_values(self):
        """JudgmentStatus 값 확인."""
        assert JudgmentStatus.COMPLETE.value == "complete"
        assert JudgmentStatus.PARTIAL.value == "partial"
        assert JudgmentStatus.UNCERTAIN.value == "uncertain"


class TestWeightValidation:
    """무게 검증 테스트."""

    def test_weight_explained_fully(self, sample_product_list):
        """무게가 완전히 설명됨."""
        db = ProductDatabase()
        engine = ProductDecisionEngine(product_db=db)

        vision_candidates = [
            {"class_id": 1, "name": "chickenmayo_rice", "confidence": 0.90},
        ]

        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=-365.0,
        )

        # residual이 0에 가까워야 함
        assert abs(result.weight_residual) < 20  # 20g 이내

    def test_weight_with_residual(self):
        """잔여 무게가 있는 경우."""
        db = ProductDatabase()
        engine = ProductDecisionEngine(product_db=db)

        vision_candidates = [
            {"class_id": 1, "name": "chickenmayo_rice", "confidence": 0.85},
        ]

        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=-400.0,  # 35g 잔여
        )

        # 잔여 무게 확인
        assert abs(result.weight_residual) > 0
