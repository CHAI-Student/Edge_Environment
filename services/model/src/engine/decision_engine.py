"""
Product Decision Engine.

최종 상품 결정 엔진.

Vision 후보군 + 무게 검증을 결합하여 최종 상품과 개수를 결정합니다.

전략:
1. 단일 상품 매칭 우선 시도
2. 실패 시 다중 상품 조합 시도
3. 완전/불완전 상태 판별
4. Vision 실패 시 Loadcell-only 폴백 (무게로 최근접 상품 추정)
5. Node.js 응답 형식으로 결과 반환
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING
import logging
import time

from .models import (
    EnsembleResult,
    CountEstimate,
    ProductJudgment,
    JudgmentResult,
    JudgmentStatus,
)
from core.config import config

# Lazy import to avoid circular dependency
if TYPE_CHECKING:
    from database.product_db import ProductDatabase

logger = logging.getLogger(__name__)


def _get_product_database():
    """Lazy import ProductDatabase to avoid circular import."""
    from database.product_db import ProductDatabase
    return ProductDatabase


def _get_count_calculator():
    """Lazy import WeightBasedCountCalculator to avoid circular import."""
    from weight.count_calculator import WeightBasedCountCalculator
    return WeightBasedCountCalculator


class ProductDecisionEngine:
    """
    최종 상품 결정 엔진.

    Vision 후보군과 무게 검증을 결합하여 최종 상품을 결정합니다.
    """

    # 신뢰도 가중치
    VISION_WEIGHT = 0.4      # Vision 신뢰도 가중치
    WEIGHT_MATCH_WEIGHT = 0.5  # 무게 매칭 가중치
    COUNT_WEIGHT = 0.1       # 개수 합리성 가중치

    def __init__(
        self,
        product_db: Optional[ProductDatabase] = None,
        tolerance_percent: Optional[float] = None,
        confidence_threshold: float = 0.3,
        max_combination_size: Optional[int] = None,
        min_weight_change: Optional[float] = None,
        partial_threshold: float = 0.7,
    ):
        """
        판단 엔진 초기화.

        Args:
            product_db: 상품 데이터베이스
            tolerance_percent: 허용 오차 비율 (기본값 10%)
            confidence_threshold: 최소 신뢰도 임계값 (기본값 0.3)
            max_combination_size: 최대 조합 크기 (기본값 2)
            min_weight_change: 최소 무게 변화량 (기본값 5g)
            partial_threshold: PARTIAL/UNCERTAIN 구분 임계값 (기본값 0.7)
        """
        if product_db is None:
            ProductDatabase = _get_product_database()
            self.product_db = ProductDatabase()
        else:
            self.product_db = product_db
        self.tolerance_percent = tolerance_percent or config.weight.tolerance_percent
        self.confidence_threshold = confidence_threshold
        self.max_combination_size = max_combination_size or config.weight.max_combination_size
        self.min_weight_change = min_weight_change or config.weight.min_weight_change
        self.partial_threshold = partial_threshold

        WeightBasedCountCalculator = _get_count_calculator()
        self.count_calculator = WeightBasedCountCalculator(
            product_db=self.product_db,
            tolerance_percent=self.tolerance_percent,
            tolerance_grams=config.weight.tolerance_grams,  # 고정 허용 오차 (기본 5g)
        )

    def judge(
        self,
        vision_candidates: List[EnsembleResult],
        delta_weight: float,
        vision_only: bool = False,
    ) -> JudgmentResult:
        """
        상품 판단 수행.

        Args:
            vision_candidates: Multi-View Ensemble 결과 (Top-5)
            delta_weight: 무게 변화량 (음수 = 제거)
            vision_only: Vision 전용 모드 (로드셀 없이 카메라만 사용)

        Returns:
            JudgmentResult (Node.js 전달용)
        """
        timestamp = time.time()
        abs_weight = abs(delta_weight)

        logger.info(f"[ENGINE] ========== 판단 엔진 ==========")
        logger.info(
            f"[ENGINE] 후보: {len(vision_candidates)}개, "
            f"delta_weight={delta_weight:.1f}g, vision_only={vision_only}"
        )

        # Vision 전용 모드: 카메라만으로 판단
        if vision_only:
            return self._judge_vision_only(vision_candidates, timestamp)

        # 1. 후보군이 없는 경우 → Loadcell-only 폴백
        if not vision_candidates:
            logger.warning("No vision candidates provided, trying loadcell-only fallback")
            return self.judge_by_weight_only(delta_weight, timestamp)

        # 2. 무게 변화가 없는 경우
        if abs_weight < self.min_weight_change:
            logger.info(f"Weight change too small: {abs_weight:.1f}g < {self.min_weight_change}g")
            return self._create_no_detection_result(delta_weight, timestamp)

        # 3. 개수 계산 (각 후보별)
        estimates = self.count_calculator.calculate(vision_candidates, delta_weight)

        if not estimates:
            logger.warning("No valid count estimates, trying loadcell-only fallback")
            return self.judge_by_weight_only(delta_weight, timestamp)

        # 4. 단일 상품 매칭 시도
        logger.info(f"[ENGINE] 전략: single_product_match 시도...")
        single_result = self._try_single_product_match(
            estimates, delta_weight, timestamp
        )
        if single_result and single_result.status == JudgmentStatus.COMPLETE:
            logger.info(f"[ENGINE] 단일 상품 매칭 성공: {single_result.products[0].name}")
            return single_result

        # 5. 다중 상품 조합 시도
        logger.info(f"[ENGINE] 전략: combination_match 시도...")
        combo_result = self._try_combination_match(
            vision_candidates, delta_weight, timestamp
        )
        if combo_result and combo_result.status == JudgmentStatus.COMPLETE:
            names = [p.name for p in combo_result.products]
            logger.info(f"[ENGINE] 조합 매칭 성공: {names}")
            return combo_result

        # 6. 불완전 결과 반환 (최선의 추정)
        logger.info(f"[ENGINE] 전략: partial_result 반환 (매칭 실패)")
        return self._create_partial_result(estimates, delta_weight, timestamp)

    def _judge_vision_only(
        self,
        vision_candidates: List[EnsembleResult],
        timestamp: float,
    ) -> JudgmentResult:
        """
        Vision 전용 판단 (로드셀 없이 카메라만 사용).

        무게 검증 없이 Vision 신뢰도만으로 상품을 판단합니다.
        개수는 1로 고정되며, 신뢰도는 Vision 신뢰도의 70%로 감소합니다.

        YOLO class_id 기반 조회:
        1. get_by_yolo_class_id로 매핑된 상품 조회
        2. 실패 시 get_by_yolo_class_name으로 폴백
        3. 최종 실패 시 Vision 결과에서 직접 생성

        Args:
            vision_candidates: Vision 후보군
            timestamp: 판단 시각

        Returns:
            JudgmentResult (status: PARTIAL, 무게 검증 없음)
        """
        logger.info(f"Vision-only judgment: {len(vision_candidates)} candidates")

        if not vision_candidates:
            logger.warning("No vision candidates for vision-only judgment")
            return self._create_no_detection_result(0.0, timestamp)

        # 후보군 로그 출력
        for i, c in enumerate(vision_candidates[:5]):
            logger.debug(
                f"  Candidate {i+1}: class_id={c.class_id}, name={c.class_name}, "
                f"conf={c.combined_confidence:.3f}"
            )

        # 가장 높은 신뢰도의 후보 선택
        best_candidate = max(vision_candidates, key=lambda c: c.combined_confidence)

        if best_candidate.combined_confidence < self.confidence_threshold:
            logger.info(
                f"Vision confidence too low: {best_candidate.combined_confidence:.3f} "
                f"< {self.confidence_threshold}"
            )
            return self._create_no_detection_result(0.0, timestamp)

        # 상품 정보 조회 (YOLO 매핑 우선)
        # 1. YOLO class_id로 매핑된 상품 조회
        product = self.product_db.get_by_yolo_class_id(best_candidate.class_id)

        # 2. 폴백: YOLO 클래스명으로 조회
        if product is None:
            product = self.product_db.get_by_yolo_class_name(best_candidate.class_name)
            if product:
                logger.debug(
                    f"Found product by yolo_class_name: {best_candidate.class_name} -> "
                    f"product_id={product.product_id}, name={product.name}"
                )

        # 3. 폴백: 기존 방식 (product_id = class_id)
        if product is None:
            product = self.product_db.get_product(best_candidate.class_id)
            if product:
                logger.debug(
                    f"Found product by class_id as product_id: {best_candidate.class_id} -> "
                    f"name={product.name}"
                )

        # ProductDatabase에 없으면 Vision 결과에서 직접 생성 (fallback)
        if product is None:
            logger.warning(
                f"Product not found in DB for class_id={best_candidate.class_id}, "
                f"using Vision class_name as fallback: {best_candidate.class_name}"
            )
            # Vision 전용: 신뢰도 70%로 감소, 개수는 1로 고정
            confidence = best_candidate.combined_confidence * 0.7
            count = 1

            # Vision 결과에서 상품 정보 생성 (가격은 0원, 무게는 0g)
            product_judgment = ProductJudgment(
                product_id=best_candidate.class_id,
                name=best_candidate.class_name,
                count=count,
                unit_price=0,  # 가격 미정
                total_price=0,
                confidence=confidence,
                unit_weight=0.0,  # 무게 미정
            )

            logger.info(
                f"Vision-only result (fallback): {best_candidate.class_name}, "
                f"class_id={best_candidate.class_id}, "
                f"vision_conf={best_candidate.combined_confidence:.3f}, "
                f"final_conf={confidence:.3f}, count={count}"
            )

            return JudgmentResult(
                products=[product_judgment],
                total_price=0,
                confidence=confidence,
                status=JudgmentStatus.PARTIAL,  # 무게 미검증
                weight_delta=0.0,
                weight_explained=0.0,
                weight_residual=0.0,
                timestamp=timestamp,
            )

        # Vision 전용: 신뢰도 70%로 감소, 개수는 1로 고정
        confidence = best_candidate.combined_confidence * 0.7
        count = 1  # 무게 없이 개수 추정 불가

        # IF11 매핑된 상품 정보 사용 (가격, 무게)
        logger.info(
            f"Vision-only result: {product.name} (product_id={product.product_id}), "
            f"price={product.price}원, weight={product.weight}g, "
            f"vision_conf={best_candidate.combined_confidence:.3f}, "
            f"final_conf={confidence:.3f}, count={count}, "
            f"yolo_class_id={best_candidate.class_id}, product_idx={product.product_idx}"
        )

        product_judgment = ProductJudgment(
            product_id=product.product_id,
            name=product.name,
            count=count,
            unit_price=product.price,
            total_price=product.price * count,
            confidence=confidence,
            unit_weight=product.weight,
        )

        return JudgmentResult(
            products=[product_judgment],
            total_price=product_judgment.total_price,
            confidence=confidence,
            status=JudgmentStatus.PARTIAL,  # 무게 미검증
            weight_delta=0.0,  # 무게 데이터 없음
            weight_explained=0.0,
            weight_residual=0.0,
            timestamp=timestamp,
        )

    def judge_by_weight_only(
        self,
        delta_weight: float,
        timestamp: Optional[float] = None,
    ) -> JudgmentResult:
        """
        무게만으로 가장 가까운 상품 추정 (Vision 실패 시 폴백).

        모든 상품 중 무게 변화량과 가장 유사한 무게를 가진 상품을 찾습니다.
        tolerance_percent 범위 내에서 매칭하며, 개수도 추정합니다.

        Args:
            delta_weight: 무게 변화량 (음수 = 제거)
            timestamp: 판단 시각 (기본값: 현재 시각)

        Returns:
            JudgmentResult (status: PARTIAL 또는 UNCERTAIN)
        """
        if timestamp is None:
            timestamp = time.time()

        abs_weight = abs(delta_weight)

        logger.info(f"Loadcell-only fallback: delta_weight={delta_weight:.1f}g")

        # 무게 변화가 너무 작은 경우
        if abs_weight < self.min_weight_change:
            logger.info(f"Weight change too small for fallback: {abs_weight:.1f}g")
            return self._create_no_detection_result(delta_weight, timestamp)

        # 모든 상품에서 가장 가까운 무게 찾기
        all_products = self.product_db.get_all_products()

        if not all_products:
            logger.warning("No products in database for fallback")
            return self._create_no_detection_result(delta_weight, timestamp)

        best_match = None
        best_error = float('inf')
        best_count = 0

        for product in all_products:
            if product.weight <= 0:
                continue

            # 개수 계산: count = round(delta / unit_weight)
            estimated_count = max(1, round(abs_weight / product.weight))
            expected_weight = product.weight * estimated_count
            error = abs(abs_weight - expected_weight)
            error_rate = error / expected_weight if expected_weight > 0 else 1.0

            # tolerance 범위 내에서 더 좋은 매칭 찾기
            if error_rate <= self.tolerance_percent and error < best_error:
                best_match = product
                best_error = error
                best_count = estimated_count

        if best_match is None:
            # tolerance 범위 밖이라도 가장 가까운 상품 반환 (UNCERTAIN)
            logger.info("No product within tolerance, finding closest match")
            for product in all_products:
                if product.weight <= 0:
                    continue

                estimated_count = max(1, round(abs_weight / product.weight))
                expected_weight = product.weight * estimated_count
                error = abs(abs_weight - expected_weight)

                if error < best_error:
                    best_match = product
                    best_error = error
                    best_count = estimated_count

        if best_match is None:
            logger.warning("Could not find any matching product by weight")
            return self._create_no_detection_result(delta_weight, timestamp)

        expected_weight = best_match.weight * best_count
        error_rate = best_error / expected_weight if expected_weight > 0 else 1.0
        match_score = max(0.0, 1.0 - error_rate)

        # 상태 결정: tolerance 범위 내면 PARTIAL, 아니면 UNCERTAIN
        if error_rate <= self.tolerance_percent:
            status = JudgmentStatus.PARTIAL
            confidence = match_score * 0.7  # Vision 없이 최대 70%
        else:
            status = JudgmentStatus.UNCERTAIN
            confidence = match_score * 0.5  # tolerance 밖이면 최대 50%

        logger.info(
            f"Loadcell-only result: {best_match.name} x {best_count}, "
            f"expected={expected_weight:.1f}g, actual={abs_weight:.1f}g, "
            f"error={best_error:.1f}g ({error_rate*100:.1f}%), status={status.value}"
        )

        product_judgment = ProductJudgment(
            product_id=best_match.product_id,
            name=best_match.name,
            count=best_count,
            unit_price=best_match.price,
            total_price=best_match.price * best_count,
            confidence=confidence,
            unit_weight=best_match.weight,
        )

        return JudgmentResult(
            products=[product_judgment],
            total_price=product_judgment.total_price,
            confidence=confidence,
            status=status,
            weight_delta=delta_weight,
            weight_explained=expected_weight,
            weight_residual=best_error,
            timestamp=timestamp,
        )

    def _try_single_product_match(
        self,
        estimates: List[CountEstimate],
        delta_weight: float,
        timestamp: float,
    ) -> Optional[JudgmentResult]:
        """
        단일 상품 매칭 시도.

        검증된(validated=True) 추정 중 가장 높은 match_score를 선택.
        """
        validated_estimates = [e for e in estimates if e.validated]

        if not validated_estimates:
            return None

        best = validated_estimates[0]

        confidence = self._calculate_fusion_confidence(
            vision_score=best.vision_confidence,
            weight_score=best.match_score,
            count=best.count,
        )

        if confidence < self.confidence_threshold:
            logger.info(f"[ENGINE] 신뢰도 부족: {confidence:.3f} < {self.confidence_threshold}")
            return None

        product = self._create_product_judgment(best, confidence)

        logger.info(
            f"[ENGINE] 최종: status=COMPLETE, products=1, confidence={confidence:.3f}"
        )

        return JudgmentResult(
            products=[product],
            total_price=product.total_price,
            confidence=confidence,
            status=JudgmentStatus.COMPLETE,
            weight_delta=delta_weight,
            weight_explained=best.expected_weight,
            weight_residual=abs(abs(delta_weight) - best.expected_weight),
            timestamp=timestamp,
        )

    def _try_combination_match(
        self,
        candidates: List[EnsembleResult],
        delta_weight: float,
        timestamp: float,
    ) -> Optional[JudgmentResult]:
        """다중 상품 조합 매칭 시도."""
        combination = self.count_calculator.calculate_combination(
            candidates=candidates,
            delta_weight=delta_weight,
            max_combination_size=self.max_combination_size,
        )

        if not combination:
            return None

        products = []
        total_price = 0
        total_explained = 0.0

        for estimate in combination:
            confidence = self._calculate_fusion_confidence(
                vision_score=estimate.vision_confidence,
                weight_score=estimate.match_score,
                count=estimate.count,
            )
            product = self._create_product_judgment(estimate, confidence)
            products.append(product)
            total_price += product.total_price
            total_explained += estimate.expected_weight

        avg_confidence = sum(p.confidence for p in products) / len(products)

        logger.info(
            f"[ENGINE] 최종: status=COMPLETE, products={len(products)}, "
            f"confidence={avg_confidence:.3f}"
        )

        return JudgmentResult(
            products=products,
            total_price=total_price,
            confidence=avg_confidence,
            status=JudgmentStatus.COMPLETE,
            weight_delta=delta_weight,
            weight_explained=total_explained,
            weight_residual=abs(abs(delta_weight) - total_explained),
            timestamp=timestamp,
        )

    def _create_partial_result(
        self,
        estimates: List[CountEstimate],
        delta_weight: float,
        timestamp: float,
    ) -> JudgmentResult:
        """불완전 결과 생성."""
        if not estimates:
            return self._create_no_detection_result(delta_weight, timestamp)

        best = estimates[0]

        confidence = self._calculate_fusion_confidence(
            vision_score=best.vision_confidence,
            weight_score=best.match_score,
            count=best.count,
        )

        if best.match_score > self.partial_threshold:
            status = JudgmentStatus.PARTIAL
        else:
            status = JudgmentStatus.UNCERTAIN

        product = self._create_product_judgment(best, confidence)

        return JudgmentResult(
            products=[product],
            total_price=product.total_price,
            confidence=confidence,
            status=status,
            weight_delta=delta_weight,
            weight_explained=best.expected_weight,
            weight_residual=abs(abs(delta_weight) - best.expected_weight),
            timestamp=timestamp,
        )

    def _create_no_detection_result(
        self,
        delta_weight: float,
        timestamp: float,
    ) -> JudgmentResult:
        """감지된 상품 없음 결과 생성."""
        return JudgmentResult(
            products=[],
            total_price=0,
            confidence=0.0,
            status=JudgmentStatus.NO_DETECTION,
            weight_delta=delta_weight,
            weight_explained=0.0,
            weight_residual=abs(delta_weight),
            timestamp=timestamp,
        )

    def _create_product_judgment(
        self,
        estimate: CountEstimate,
        confidence: float,
    ) -> ProductJudgment:
        """CountEstimate에서 ProductJudgment 생성."""
        price = self.product_db.get_price(estimate.product_id)
        total_price = price * estimate.count

        return ProductJudgment(
            product_id=estimate.product_id,
            name=estimate.product_name,
            count=estimate.count,
            unit_price=price,
            total_price=total_price,
            confidence=confidence,
            unit_weight=estimate.unit_weight,
        )

    def _calculate_fusion_confidence(
        self,
        vision_score: float,
        weight_score: float,
        count: int,
    ) -> float:
        """
        퓨전 신뢰도 계산.

        가중 평균:
        - Vision 신뢰도: 40%
        - 무게 매칭 점수: 50%
        - 개수 합리성: 10%
        """
        vision_normalized = min(max(vision_score, 0.0), 1.0)
        weight_normalized = min(max(weight_score, 0.0), 1.0)

        if count <= 3:
            count_score = 1.0
        else:
            count_score = max(0.0, 1.0 - (count - 3) * 0.1)

        confidence = (
            self.VISION_WEIGHT * vision_normalized +
            self.WEIGHT_MATCH_WEIGHT * weight_normalized +
            self.COUNT_WEIGHT * count_score
        )

        logger.debug(f"[ENGINE] 신뢰도 계산:")
        logger.debug(
            f"  vision={vision_normalized:.3f} × {self.VISION_WEIGHT} = "
            f"{vision_normalized * self.VISION_WEIGHT:.3f}"
        )
        logger.debug(
            f"  weight={weight_normalized:.3f} × {self.WEIGHT_MATCH_WEIGHT} = "
            f"{weight_normalized * self.WEIGHT_MATCH_WEIGHT:.3f}"
        )
        logger.debug(
            f"  count={count_score:.3f} × {self.COUNT_WEIGHT} = "
            f"{count_score * self.COUNT_WEIGHT:.3f}"
        )
        logger.debug(f"  total = {min(confidence, 1.0):.3f}")

        return min(confidence, 1.0)
