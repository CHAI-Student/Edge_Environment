"""
Weight-Based Count Calculator.

무게 변화량 기반 상품 개수 계산기.

핵심 알고리즘:
1. Vision 후보군의 각 상품에 대해 개수 추정
2. count = round(abs(delta_weight) / unit_weight)
3. 허용 오차 내 검증 (tolerance_percent)
4. match_score 계산으로 최적 후보 선별

사용 예시:
    calculator = WeightBasedCountCalculator(product_db)
    estimates = calculator.calculate(candidates, delta_weight=-365.0)
    best = estimates[0]  # 가장 높은 match_score
"""

from dataclasses import dataclass
from typing import List, Optional
import logging

from ..engine.models import EnsembleResult, CountEstimate
from ..database.product_db import ProductDatabase

logger = logging.getLogger(__name__)


class WeightBasedCountCalculator:
    """
    무게 기반 개수 계산기.

    Vision 후보군의 각 상품에 대해 무게 변화량으로 개수를 추정하고,
    허용 오차 내에서 검증합니다.

    Attributes:
        product_db: 상품 데이터베이스
        tolerance_percent: 기본 허용 오차 비율 (0.0 ~ 1.0)
        max_count: 최대 개수 제한
        min_weight_change: 최소 무게 변화량 (g)
    """

    def __init__(
        self,
        product_db: ProductDatabase,
        tolerance_percent: float = 0.10,
        max_count: int = 10,
        min_weight_change: float = 5.0,
    ):
        """
        개수 계산기 초기화.

        Args:
            product_db: 상품 데이터베이스
            tolerance_percent: 기본 허용 오차 비율 (기본값 10%)
            max_count: 최대 개수 제한 (기본값 10)
            min_weight_change: 최소 무게 변화량 (기본값 5g)
        """
        self.product_db = product_db
        self.tolerance_percent = tolerance_percent
        self.max_count = max_count
        self.min_weight_change = min_weight_change

    def calculate(
        self,
        candidates: List[EnsembleResult],
        delta_weight: float,
        use_category_tolerance: bool = True,
    ) -> List[CountEstimate]:
        """
        각 후보에 대한 개수 추정.

        Vision 후보군의 각 상품에 대해 무게 기반 개수를 계산하고,
        match_score 기준으로 정렬하여 반환합니다.

        Args:
            candidates: Multi-View Ensemble 결과 (Top-5)
            delta_weight: 무게 변화량 (음수 = 제거)
            use_category_tolerance: 카테고리별 허용 오차 사용 여부

        Returns:
            CountEstimate 리스트 (match_score 내림차순 정렬)
        """
        abs_weight = abs(delta_weight)

        # 최소 무게 변화량 체크
        if abs_weight < self.min_weight_change:
            logger.debug(f"Weight change too small: {abs_weight}g < {self.min_weight_change}g")
            return []

        estimates = []

        for candidate in candidates:
            product = self.product_db.get_product(candidate.class_id)

            if product is None:
                logger.warning(f"Product not found for class_id: {candidate.class_id}")
                continue

            if product.weight <= 0:
                logger.debug(f"Skipping product with zero weight: {product.name}")
                continue

            # 개수 추정
            count = self._estimate_count(abs_weight, product.weight)
            if count <= 0:
                continue

            # 예상 무게 계산
            expected_weight = product.weight * count
            weight_error = abs(abs_weight - expected_weight)

            # 허용 오차 결정
            if use_category_tolerance:
                tolerance = self.product_db.get_tolerance(
                    product.product_id,
                    default=self.tolerance_percent
                )
            else:
                tolerance = self.tolerance_percent

            tolerance_amount = expected_weight * tolerance

            # 검증
            validated = weight_error <= tolerance_amount

            # 매칭 점수 계산
            match_score = self._calculate_match_score(
                weight_error=weight_error,
                expected_weight=expected_weight,
                tolerance=tolerance,
                vision_confidence=candidate.combined_confidence,
            )

            estimate = CountEstimate(
                product_id=candidate.class_id,
                product_name=product.name,
                count=count,
                unit_weight=product.weight,
                expected_weight=expected_weight,
                actual_weight=abs_weight,
                match_score=match_score,
                vision_confidence=candidate.combined_confidence,
                validated=validated,
            )

            estimates.append(estimate)
            logger.debug(
                f"Estimate: {product.name} x{count}, "
                f"expected={expected_weight:.1f}g, actual={abs_weight:.1f}g, "
                f"error={weight_error:.1f}g, validated={validated}, score={match_score:.3f}"
            )

        # match_score 기준 정렬
        estimates.sort(key=lambda e: e.match_score, reverse=True)

        return estimates

    def _estimate_count(self, abs_weight: float, unit_weight: float) -> int:
        """
        수량 추정 (반올림).

        Args:
            abs_weight: 절대 무게 변화량 (g)
            unit_weight: 단위 무게 (g)

        Returns:
            추정 개수 (1 ~ max_count)
        """
        if unit_weight <= 0:
            return 0

        count = round(abs_weight / unit_weight)

        # 범위 제한
        if count < 1:
            return 0
        if count > self.max_count:
            return self.max_count

        return count

    def _calculate_match_score(
        self,
        weight_error: float,
        expected_weight: float,
        tolerance: float,
        vision_confidence: float,
    ) -> float:
        """
        매칭 점수 계산.

        점수 구성:
        - 무게 매칭 점수 (50%): 오차가 적을수록 높음
        - Vision 신뢰도 (40%): 앙상블 결과 신뢰도
        - 개수 합리성 (10%): 개수가 적을수록 높음 (단순성 선호)

        Args:
            weight_error: 무게 오차 (g)
            expected_weight: 예상 무게 (g)
            tolerance: 허용 오차 비율
            vision_confidence: Vision 신뢰도

        Returns:
            매칭 점수 (0.0 ~ 1.0)
        """
        # 1. 무게 매칭 점수 (0.0 ~ 1.0)
        if expected_weight <= 0:
            weight_score = 0.0
        else:
            error_rate = weight_error / expected_weight
            # 허용 오차의 2배까지 선형 감소
            weight_score = max(0.0, 1.0 - (error_rate / (2 * tolerance)))

        # 2. Vision 신뢰도 (0.0 ~ 1.0)
        vision_score = min(max(vision_confidence, 0.0), 1.0)

        # 3. 가중 평균
        # 무게 매칭 50%, Vision 40%, 기타 10%
        match_score = (
            weight_score * 0.5 +
            vision_score * 0.4 +
            0.1  # 기본 점수
        )

        return min(match_score, 1.0)

    def calculate_combination(
        self,
        candidates: List[EnsembleResult],
        delta_weight: float,
        max_combination_size: int = 2,
    ) -> Optional[List[CountEstimate]]:
        """
        다중 상품 조합 계산.

        단일 상품으로 무게를 설명할 수 없을 때,
        2개 이상의 상품 조합으로 시도합니다.

        전략:
        1. 동일 상품 다중 개수 (A x N)
        2. 서로 다른 상품 조합 (A x 1 + B x 1)
        3. 서로 다른 상품 다중 개수 (A x N + B x M)

        Args:
            candidates: Multi-View Ensemble 결과
            delta_weight: 무게 변화량
            max_combination_size: 최대 조합 크기 (기본값 2)

        Returns:
            매칭되는 CountEstimate 리스트 또는 None
        """
        from itertools import combinations, product as iterproduct

        abs_weight = abs(delta_weight)

        if abs_weight < self.min_weight_change:
            return None

        # 후보군에서 상품 정보 추출
        product_candidates = []
        for candidate in candidates[:5]:  # 상위 5개만 고려
            prod = self.product_db.get_product(candidate.class_id)
            if prod and prod.weight > 0:
                product_candidates.append((candidate, prod))

        if not product_candidates:
            return None

        best_combination = None
        best_error = float("inf")
        best_score = 0.0

        # 전략 1: 동일 상품 다중 개수 (이미 단일 매칭에서 처리됨, 스킵)

        # 전략 2 & 3: 서로 다른 상품 조합 (다양한 개수)
        if len(product_candidates) >= 2:
            for (cand1, prod1), (cand2, prod2) in combinations(product_candidates, 2):
                # 각 상품 1~3개씩 조합 시도
                for count1, count2 in iterproduct(range(1, 4), range(1, 4)):
                    combined_weight = prod1.weight * count1 + prod2.weight * count2
                    error = abs(abs_weight - combined_weight)
                    tolerance = combined_weight * self.tolerance_percent

                    if error <= tolerance:
                        # 매칭 점수 계산 (오차 적을수록 + 개수 적을수록 높음)
                        error_score = 1.0 - (error / combined_weight) if combined_weight > 0 else 0
                        count_penalty = 1.0 - ((count1 + count2 - 2) * 0.1)  # 2개일 때 최고
                        avg_confidence = (cand1.combined_confidence + cand2.combined_confidence) / 2
                        score = error_score * 0.5 + avg_confidence * 0.4 + count_penalty * 0.1

                        if error < best_error or (error == best_error and score > best_score):
                            best_error = error
                            best_score = score

                            # 각 상품의 기여 무게 비율로 actual_weight 분배
                            weight1 = prod1.weight * count1
                            weight2 = prod2.weight * count2
                            total_expected = weight1 + weight2

                            best_combination = [
                                CountEstimate(
                                    product_id=cand1.class_id,
                                    product_name=prod1.name,
                                    count=count1,
                                    unit_weight=prod1.weight,
                                    expected_weight=weight1,
                                    actual_weight=abs_weight * (weight1 / total_expected),
                                    match_score=self._calculate_match_score(
                                        weight_error=error * (weight1 / total_expected),
                                        expected_weight=weight1,
                                        tolerance=self.tolerance_percent,
                                        vision_confidence=cand1.combined_confidence,
                                    ),
                                    vision_confidence=cand1.combined_confidence,
                                    validated=True,
                                ),
                                CountEstimate(
                                    product_id=cand2.class_id,
                                    product_name=prod2.name,
                                    count=count2,
                                    unit_weight=prod2.weight,
                                    expected_weight=weight2,
                                    actual_weight=abs_weight * (weight2 / total_expected),
                                    match_score=self._calculate_match_score(
                                        weight_error=error * (weight2 / total_expected),
                                        expected_weight=weight2,
                                        tolerance=self.tolerance_percent,
                                        vision_confidence=cand2.combined_confidence,
                                    ),
                                    vision_confidence=cand2.combined_confidence,
                                    validated=True,
                                ),
                            ]

        if best_combination:
            products_str = " + ".join(
                f"{e.product_name}x{e.count}" for e in best_combination
            )
            logger.info(
                f"Found combination match: {products_str}, "
                f"error={best_error:.1f}g, score={best_score:.3f}"
            )

        return best_combination

    def validate_estimate(self, estimate: CountEstimate) -> bool:
        """
        개수 추정 결과 검증.

        Args:
            estimate: CountEstimate 인스턴스

        Returns:
            검증 통과 여부
        """
        # 기본 검증
        if estimate.count <= 0:
            return False

        if estimate.count > self.max_count:
            return False

        # 오차율 검증
        tolerance = self.product_db.get_tolerance(
            estimate.product_id,
            default=self.tolerance_percent
        )

        return estimate.error_rate <= tolerance
