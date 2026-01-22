"""
Product Decision Engine.

최종 상품 결정 엔진.

Vision 후보군 + 무게 검증을 결합하여 최종 상품과 개수를 결정합니다.

전략:
1. 단일 상품 매칭 우선 시도
2. 실패 시 다중 상품 조합 시도
3. 완전/불완전 상태 판별
4. Node.js 응답 형식으로 결과 반환

사용 예시:
    engine = ProductDecisionEngine(product_db)
    result = engine.judge(candidates, delta_weight=-365.0)
    response = result.to_node_response()
"""

from typing import List, Optional
import logging
import time

from .models import (
    EnsembleResult,
    CountEstimate,
    ProductJudgment,
    JudgmentResult,
    JudgmentStatus,
)
from ..database.product_db import ProductDatabase
from ..weight.count_calculator import WeightBasedCountCalculator

logger = logging.getLogger(__name__)


class ProductDecisionEngine:
    """
    최종 상품 결정 엔진.

    Vision 후보군과 무게 검증을 결합하여 최종 상품을 결정합니다.

    Attributes:
        product_db: 상품 데이터베이스
        count_calculator: 개수 계산기
        tolerance_percent: 허용 오차 비율
        confidence_threshold: 최소 신뢰도 임계값
        min_weight_change: 최소 무게 변화량 (g)
        partial_threshold: PARTIAL/UNCERTAIN 구분 임계값
    """

    # 신뢰도 가중치
    VISION_WEIGHT = 0.4      # Vision 신뢰도 가중치
    WEIGHT_MATCH_WEIGHT = 0.5  # 무게 매칭 가중치
    COUNT_WEIGHT = 0.1       # 개수 합리성 가중치

    def __init__(
        self,
        product_db: ProductDatabase,
        tolerance_percent: float = 0.10,
        confidence_threshold: float = 0.3,
        max_combination_size: int = 2,
        min_weight_change: float = 5.0,
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
        self.product_db = product_db
        self.tolerance_percent = tolerance_percent
        self.confidence_threshold = confidence_threshold
        self.max_combination_size = max_combination_size
        self.min_weight_change = min_weight_change
        self.partial_threshold = partial_threshold

        self.count_calculator = WeightBasedCountCalculator(
            product_db=product_db,
            tolerance_percent=tolerance_percent,
        )

    def judge(
        self,
        vision_candidates: List[EnsembleResult],
        delta_weight: float,
    ) -> JudgmentResult:
        """
        상품 판단 수행.

        Args:
            vision_candidates: Multi-View Ensemble 결과 (Top-5)
            delta_weight: 무게 변화량 (음수 = 제거)

        Returns:
            JudgmentResult (Node.js 전달용)
        """
        timestamp = time.time()
        abs_weight = abs(delta_weight)

        logger.info(
            f"Starting judgment: {len(vision_candidates)} candidates, "
            f"delta_weight={delta_weight:.1f}g"
        )

        # 1. 후보군이 없는 경우
        if not vision_candidates:
            logger.warning("No vision candidates provided")
            return self._create_no_detection_result(delta_weight, timestamp)

        # 2. 무게 변화가 없는 경우
        if abs_weight < self.min_weight_change:
            logger.info(f"Weight change too small: {abs_weight:.1f}g < {self.min_weight_change}g")
            return self._create_no_detection_result(delta_weight, timestamp)

        # 3. 개수 계산 (각 후보별)
        estimates = self.count_calculator.calculate(vision_candidates, delta_weight)

        if not estimates:
            logger.warning("No valid count estimates")
            return self._create_no_detection_result(delta_weight, timestamp)

        # 4. 단일 상품 매칭 시도
        single_result = self._try_single_product_match(
            estimates, delta_weight, timestamp
        )
        if single_result and single_result.status == JudgmentStatus.COMPLETE:
            logger.info(f"Single product match success: {single_result.products[0].name}")
            return single_result

        # 5. 다중 상품 조합 시도
        combo_result = self._try_combination_match(
            vision_candidates, delta_weight, timestamp
        )
        if combo_result and combo_result.status == JudgmentStatus.COMPLETE:
            names = [p.name for p in combo_result.products]
            logger.info(f"Combination match success: {names}")
            return combo_result

        # 6. 불완전 결과 반환 (최선의 추정)
        logger.info("Returning partial/uncertain result")
        return self._create_partial_result(estimates, delta_weight, timestamp)

    def _try_single_product_match(
        self,
        estimates: List[CountEstimate],
        delta_weight: float,
        timestamp: float,
    ) -> Optional[JudgmentResult]:
        """
        단일 상품 매칭 시도.

        검증된(validated=True) 추정 중 가장 높은 match_score를 선택.

        Args:
            estimates: CountEstimate 리스트
            delta_weight: 무게 변화량
            timestamp: 타임스탬프

        Returns:
            JudgmentResult 또는 None
        """
        # 검증된 추정 필터링
        validated_estimates = [e for e in estimates if e.validated]

        if not validated_estimates:
            return None

        # 최고 점수 선택
        best = validated_estimates[0]  # 이미 match_score 정렬됨

        # confidence 계산
        confidence = self._calculate_fusion_confidence(
            vision_score=best.vision_confidence,
            weight_score=best.match_score,
            count=best.count,
        )

        # 최소 신뢰도 체크
        if confidence < self.confidence_threshold:
            logger.debug(f"Confidence too low: {confidence:.3f} < {self.confidence_threshold}")
            return None

        # ProductJudgment 생성
        product = self._create_product_judgment(best, confidence)

        # JudgmentResult 생성
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
        """
        다중 상품 조합 매칭 시도.

        Args:
            candidates: Vision 후보군
            delta_weight: 무게 변화량
            timestamp: 타임스탬프

        Returns:
            JudgmentResult 또는 None
        """
        combination = self.count_calculator.calculate_combination(
            candidates=candidates,
            delta_weight=delta_weight,
            max_combination_size=self.max_combination_size,
        )

        if not combination:
            return None

        # 각 상품에 대해 ProductJudgment 생성
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

        # 전체 confidence는 개별 confidence의 평균
        avg_confidence = sum(p.confidence for p in products) / len(products)

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
        """
        불완전 결과 생성.

        검증되지 않았지만 가장 높은 match_score를 가진 추정을 사용.

        Args:
            estimates: CountEstimate 리스트
            delta_weight: 무게 변화량
            timestamp: 타임스탬프

        Returns:
            JudgmentResult (status=PARTIAL 또는 UNCERTAIN)
        """
        if not estimates:
            return self._create_no_detection_result(delta_weight, timestamp)

        # 최고 점수 선택
        best = estimates[0]

        # confidence 계산
        confidence = self._calculate_fusion_confidence(
            vision_score=best.vision_confidence,
            weight_score=best.match_score,
            count=best.count,
        )

        # 상태 결정 (partial_threshold 기준)
        if best.match_score > self.partial_threshold:
            status = JudgmentStatus.PARTIAL
        else:
            status = JudgmentStatus.UNCERTAIN

        # ProductJudgment 생성
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
        """
        CountEstimate에서 ProductJudgment 생성.

        Args:
            estimate: CountEstimate 인스턴스
            confidence: 계산된 신뢰도

        Returns:
            ProductJudgment 인스턴스
        """
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

        Args:
            vision_score: Vision 신뢰도 (0.0 ~ 1.0)
            weight_score: 무게 매칭 점수 (0.0 ~ 1.0)
            count: 추정 개수

        Returns:
            퓨전 신뢰도 (0.0 ~ 1.0)
        """
        # Vision 점수 정규화
        vision_normalized = min(max(vision_score, 0.0), 1.0)

        # 무게 매칭 점수 정규화
        weight_normalized = min(max(weight_score, 0.0), 1.0)

        # 개수 합리성 점수
        # 1~3개면 1.0, 그 이상은 점차 감소
        if count <= 3:
            count_score = 1.0
        else:
            count_score = max(0.0, 1.0 - (count - 3) * 0.1)

        # 가중 평균
        confidence = (
            self.VISION_WEIGHT * vision_normalized +
            self.WEIGHT_MATCH_WEIGHT * weight_normalized +
            self.COUNT_WEIGHT * count_score
        )

        return min(confidence, 1.0)

    def judge_with_request(
        self,
        vision_candidates: List[EnsembleResult],
        loadcell_weights: List[float],
        baseline_weights: List[float],
        zone_id: Optional[int] = None,
    ) -> JudgmentResult:
        """
        요청 데이터로 판단 수행.

        JudgmentRequest 대신 개별 파라미터로 호출.

        Args:
            vision_candidates: Vision 후보군
            loadcell_weights: 현재 로드셀 무게 (10채널)
            baseline_weights: 기준 로드셀 무게 (10채널)
            zone_id: Zone ID (옵션)

        Returns:
            JudgmentResult
        """
        # 무게 변화량 계산
        deltas = [
            curr - base
            for curr, base in zip(loadcell_weights, baseline_weights)
        ]

        if zone_id is not None:
            # 특정 Zone의 무게 변화량
            start_idx = zone_id * 2
            delta_weight = sum(deltas[start_idx:start_idx + 2])
        else:
            # 전체 무게 변화량
            delta_weight = sum(deltas)

        return self.judge(vision_candidates, delta_weight)
