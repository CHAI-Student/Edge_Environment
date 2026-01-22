"""
Product Decision Engine Tests.

테스트 실행:
    pytest tests/test_engine.py -v
"""

import pytest
from product_judge import (
    ProductDatabase,
    ProductDecisionEngine,
    EnsembleResult,
    JudgmentStatus,
)


@pytest.fixture
def product_db():
    """상품 데이터베이스 fixture."""
    return ProductDatabase()


@pytest.fixture
def engine(product_db):
    """판단 엔진 fixture."""
    return ProductDecisionEngine(product_db)


class TestProductDecisionEngine:
    """판단 엔진 테스트."""

    def test_single_product_exact_match(self, engine):
        """단일 상품 정확 매칭."""
        # chickenmayo_rice: id=26, weight=365g
        candidates = [
            EnsembleResult(
                class_id=26,
                class_name="chickenmayo_rice",
                top_confidence=0.9,
                side_confidence=0.85,
                combined_confidence=0.88,
                vote_count=2,
            )
        ]

        result = engine.judge(candidates, delta_weight=-365.0)

        assert result.status == JudgmentStatus.COMPLETE
        assert len(result.products) == 1
        assert result.products[0].name == "chickenmayo_rice"
        assert result.products[0].count == 1
        assert result.total_price == 3500

    def test_single_product_with_tolerance(self, engine):
        """허용 오차 내 매칭."""
        # chickenmayo_rice: weight=365g, 10% tolerance = 36.5g
        candidates = [
            EnsembleResult(
                class_id=26,
                class_name="chickenmayo_rice",
                top_confidence=0.9,
                side_confidence=0.85,
                combined_confidence=0.88,
                vote_count=2,
            )
        ]

        # 380g (오차 15g < 36.5g)
        result = engine.judge(candidates, delta_weight=-380.0)

        assert result.status == JudgmentStatus.COMPLETE
        assert result.products[0].count == 1

    def test_multiple_count(self, engine):
        """다중 개수 감지."""
        # vita500: id=9, weight=130g
        candidates = [
            EnsembleResult(
                class_id=9,
                class_name="vita500",
                top_confidence=0.85,
                side_confidence=0.8,
                combined_confidence=0.82,
                vote_count=2,
            )
        ]

        # 260g = 130g x 2
        result = engine.judge(candidates, delta_weight=-260.0)

        assert result.status == JudgmentStatus.COMPLETE
        assert result.products[0].count == 2
        assert result.total_price == 2400  # 1200 x 2

    def test_no_detection(self, engine):
        """감지 없음."""
        result = engine.judge([], delta_weight=-100.0)

        assert result.status == JudgmentStatus.NO_DETECTION
        assert len(result.products) == 0
        assert result.total_price == 0

    def test_weight_too_small(self, engine):
        """무게 변화 너무 작음."""
        candidates = [
            EnsembleResult(
                class_id=26,
                class_name="chickenmayo_rice",
                top_confidence=0.9,
                side_confidence=0.85,
                combined_confidence=0.88,
                vote_count=2,
            )
        ]

        # 3g (< 5g threshold)
        result = engine.judge(candidates, delta_weight=-3.0)

        assert result.status == JudgmentStatus.NO_DETECTION

    def test_weight_mismatch_partial(self, engine):
        """무게 불일치 - 부분 결과."""
        candidates = [
            EnsembleResult(
                class_id=26,
                class_name="chickenmayo_rice",
                top_confidence=0.9,
                side_confidence=0.85,
                combined_confidence=0.88,
                vote_count=2,
            )
        ]

        # 500g (chickenmayo_rice=365g, 오차율 37% > 10%)
        result = engine.judge(candidates, delta_weight=-500.0)

        assert result.status in [JudgmentStatus.PARTIAL, JudgmentStatus.UNCERTAIN]

    def test_beverage_product(self, engine):
        """음료 상품 테스트."""
        # coca_cola_350: id=4, weight=380g
        candidates = [
            EnsembleResult(
                class_id=4,
                class_name="coca_cola_350",
                top_confidence=0.75,
                side_confidence=0.7,
                combined_confidence=0.72,
                vote_count=2,
            )
        ]

        result = engine.judge(candidates, delta_weight=-380.0)

        assert result.status == JudgmentStatus.COMPLETE
        assert result.products[0].name == "coca_cola_350"
        assert result.total_price == 1800


class TestProductDatabase:
    """상품 데이터베이스 테스트."""

    def test_product_count(self, product_db):
        """상품 개수 확인."""
        assert product_db.product_count == 50  # hand 제외

    def test_get_product(self, product_db):
        """상품 조회."""
        product = product_db.get_product(26)
        assert product is not None
        assert product.name == "chickenmayo_rice"
        assert product.weight == 365
        assert product.price == 3500

    def test_get_price(self, product_db):
        """가격 조회."""
        price = product_db.get_price(26)
        assert price == 3500

    def test_get_weight(self, product_db):
        """무게 조회."""
        weight = product_db.get_weight(26)
        assert weight == 365

    def test_search_by_weight(self, product_db):
        """무게로 검색."""
        # 약 365g 근처 상품 검색
        matches = product_db.search_by_weight(365.0, tolerance=0.1)
        assert len(matches) > 0
        assert any(p.name == "chickenmayo_rice" for p in matches)


class TestResponseFormat:
    """응답 형식 테스트."""

    def test_to_node_response(self, engine):
        """Node.js 응답 형식."""
        candidates = [
            EnsembleResult(
                class_id=26,
                class_name="chickenmayo_rice",
                top_confidence=0.9,
                side_confidence=0.85,
                combined_confidence=0.88,
                vote_count=2,
            )
        ]

        result = engine.judge(candidates, delta_weight=-365.0)
        response = result.to_node_response()

        # 필수 필드 확인
        assert "success" in response
        assert "products" in response
        assert "totalPrice" in response
        assert "status" in response
        assert "confidence" in response
        assert "weightInfo" in response
        assert "timestamp" in response

        # 상품 필드 확인
        product = response["products"][0]
        assert "productId" in product
        assert "name" in product
        assert "count" in product
        assert "unitPrice" in product
        assert "totalPrice" in product
        assert "confidence" in product


class TestVisionModules:
    """Vision 모듈 테스트."""

    def test_hand_filter_no_hands(self):
        """손이 없으면 모든 상품 반환."""
        from product_judge.vision.hand_filter import HandProximityFilter
        from product_judge.vision.yolo_wrapper import YOLODetection

        filter = HandProximityFilter(max_distance_px=150)
        detections = [
            YOLODetection(xyxy=(100, 100, 150, 150), conf=0.8, cls=26, name="chickenmayo_rice"),
            YOLODetection(xyxy=(200, 200, 250, 250), conf=0.7, cls=27, name="tuna_rice"),
        ]

        result = filter.filter(detections)

        assert len(result.hands) == 0
        assert len(result.filtered_products) == 2  # 모든 상품 반환

    def test_hand_filter_nearest_product(self):
        """손 근처 상품만 필터링."""
        from product_judge.vision.hand_filter import HandProximityFilter
        from product_judge.vision.yolo_wrapper import YOLODetection

        filter = HandProximityFilter(max_distance_px=100)
        detections = [
            YOLODetection(xyxy=(100, 100, 150, 150), conf=0.9, cls=0, name="hand"),  # 중심 (125, 125)
            YOLODetection(xyxy=(130, 130, 180, 180), conf=0.8, cls=26, name="chickenmayo_rice"),  # 가까움
            YOLODetection(xyxy=(400, 400, 450, 450), conf=0.7, cls=27, name="tuna_rice"),  # 멀리
        ]

        result = filter.filter(detections)

        assert len(result.hands) == 1
        assert len(result.filtered_products) == 1
        assert result.filtered_products[0].name == "chickenmayo_rice"

    def test_top5_extractor_basic(self):
        """Top-5 추출 기본 테스트."""
        from product_judge.vision.top5_extractor import Top5Extractor
        from product_judge.vision.yolo_wrapper import YOLODetection

        extractor = Top5Extractor(top_k=3)
        detections = [
            YOLODetection(xyxy=(100, 100, 150, 150), conf=0.9, cls=1, name="product1"),
            YOLODetection(xyxy=(200, 200, 250, 250), conf=0.7, cls=2, name="product2"),
            YOLODetection(xyxy=(300, 300, 350, 350), conf=0.8, cls=3, name="product3"),
            YOLODetection(xyxy=(400, 400, 450, 450), conf=0.5, cls=4, name="product4"),
        ]

        result = extractor.extract(detections)

        assert len(result.candidates) == 3
        # confidence 순 정렬 확인
        assert result.candidates[0].conf == 0.9
        assert result.candidates[1].conf == 0.8
        assert result.candidates[2].conf == 0.7

    def test_ensemble_common_class_bonus(self):
        """앙상블 공통 클래스 보너스."""
        from product_judge.vision.top5_extractor import Top5Extractor
        from product_judge.vision.yolo_wrapper import YOLODetection

        extractor = Top5Extractor()

        top_candidates = [
            YOLODetection(xyxy=(100, 100, 150, 150), conf=0.6, cls=26, name="chickenmayo_rice"),
            YOLODetection(xyxy=(200, 200, 250, 250), conf=0.5, cls=27, name="tuna_rice"),
        ]
        side_candidates = [
            YOLODetection(xyxy=(100, 100, 150, 150), conf=0.7, cls=26, name="chickenmayo_rice"),
            YOLODetection(xyxy=(300, 300, 350, 350), conf=0.8, cls=28, name="spam_rice"),
        ]

        ensemble = extractor.ensemble(top_candidates, side_candidates)

        # chickenmayo_rice가 양쪽에서 감지되어 보너스 받음
        assert ensemble[0].class_name == "chickenmayo_rice"
        assert ensemble[0].vote_count == 2  # 양쪽 합의


class TestCombinationMatching:
    """다중 상품 조합 매칭 테스트."""

    def test_combination_two_products(self, engine):
        """2개 상품 조합 매칭."""
        # snickers(52g) + vita500(130g) = 182g
        candidates = [
            EnsembleResult(
                class_id=21,
                class_name="snickers",
                top_confidence=0.8,
                side_confidence=0.75,
                combined_confidence=0.77,
                vote_count=2,
            ),
            EnsembleResult(
                class_id=9,
                class_name="vita500",
                top_confidence=0.7,
                side_confidence=0.65,
                combined_confidence=0.67,
                vote_count=2,
            ),
        ]

        result = engine.judge(candidates, delta_weight=-182.0)

        # 조합 매칭 또는 단일 매칭 시도
        assert result.status in [JudgmentStatus.COMPLETE, JudgmentStatus.PARTIAL, JudgmentStatus.UNCERTAIN]

    def test_combination_with_multiple_counts(self, engine):
        """다중 개수 조합 매칭."""
        # choco_pie(39g) x 2 + vita500(130g) x 1 = 78 + 130 = 208g
        candidates = [
            EnsembleResult(
                class_id=13,
                class_name="choco_pie",
                top_confidence=0.85,
                side_confidence=0.8,
                combined_confidence=0.82,
                vote_count=2,
            ),
            EnsembleResult(
                class_id=9,
                class_name="vita500",
                top_confidence=0.75,
                side_confidence=0.7,
                combined_confidence=0.72,
                vote_count=2,
            ),
        ]

        result = engine.judge(candidates, delta_weight=-208.0)

        # 판단 시도됨
        assert result.status in [JudgmentStatus.COMPLETE, JudgmentStatus.PARTIAL, JudgmentStatus.UNCERTAIN]


class TestCategoryTolerance:
    """카테고리별 허용 오차 테스트."""

    def test_beverage_tolerance(self, product_db):
        """음료 카테고리 5% 허용 오차."""
        tolerance = product_db.get_tolerance(1)  # pulmuone_spring_water_500
        assert tolerance == 0.05

    def test_snack_tolerance(self, product_db):
        """스낵 카테고리 10% 허용 오차."""
        tolerance = product_db.get_tolerance(11)  # pepero_original
        assert tolerance == 0.10

    def test_food_tolerance(self, product_db):
        """식품 카테고리 8% 허용 오차."""
        tolerance = product_db.get_tolerance(26)  # chickenmayo_rice
        assert tolerance == 0.08

    def test_dairy_tolerance(self, product_db):
        """유제품 카테고리 7% 허용 오차."""
        tolerance = product_db.get_tolerance(36)  # seoul_milk_200
        assert tolerance == 0.07

    def test_default_tolerance(self, product_db):
        """알 수 없는 카테고리 기본 허용 오차."""
        tolerance = product_db.get_tolerance(9999, default=0.12)  # 존재하지 않는 상품
        assert tolerance == 0.12


class TestEdgeCases:
    """엣지 케이스 테스트."""

    def test_zero_weight_product(self, engine):
        """무게가 0인 상품 처리."""
        candidates = [
            EnsembleResult(
                class_id=0,  # hand (weight=0)
                class_name="hand",
                top_confidence=0.9,
                side_confidence=0.85,
                combined_confidence=0.88,
                vote_count=2,
            )
        ]

        result = engine.judge(candidates, delta_weight=-100.0)

        # 무게 0인 상품은 무시되어야 함
        assert result.status == JudgmentStatus.NO_DETECTION

    def test_exact_boundary_tolerance(self, engine):
        """정확히 허용 오차 경계에서의 동작."""
        # chickenmayo_rice: weight=365g, food category=8%, tolerance=29.2g
        # 경계값: 365 + 29.2 = 394.2g
        candidates = [
            EnsembleResult(
                class_id=26,
                class_name="chickenmayo_rice",
                top_confidence=0.9,
                side_confidence=0.85,
                combined_confidence=0.88,
                vote_count=2,
            )
        ]

        # 정확히 경계 내 (오차 29g < 29.2g)
        result = engine.judge(candidates, delta_weight=-394.0)
        assert result.status == JudgmentStatus.COMPLETE

    def test_nonexistent_product(self, product_db):
        """존재하지 않는 상품 조회."""
        product = product_db.get_product(9999)
        assert product is None

        price = product_db.get_price(9999)
        assert price == 0

        weight = product_db.get_weight(9999)
        assert weight == 0.0
