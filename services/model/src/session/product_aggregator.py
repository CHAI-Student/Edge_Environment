"""
Product Aggregator for Door Session.

여러 TriggerResult의 상품을 통합하고, 반환 처리를 수행합니다.

합산 로직:
1. 제거(delta<0): 상품 count 증가
2. 반환(delta>0): 무게 매칭하여 count 감소

사용법:
    aggregator = ProductAggregator(weight_tolerance=3.0)
    aggregated = aggregator.aggregate(triggers)

    # 무게로 상품 찾기
    product_id = aggregator.find_product_by_weight(aggregated, 365.0)
"""

import logging
from typing import Callable, Dict, List, Optional

from .door_session import TriggerResult, AggregatedProduct
from .session_store import ProductResult

logger = logging.getLogger(__name__)


class ProductAggregator:
    """
    상품 통합 및 반환 처리.

    여러 trigger에서 감지된 상품을 합산하고,
    무게 증가(반환) 시 해당 무게의 상품을 차감합니다.
    """

    def __init__(
        self,
        weight_tolerance: float = 3.0,
        get_product_weight: Optional[Callable[[int], float]] = None,
    ):
        """
        Initialize ProductAggregator.

        Args:
            weight_tolerance: 무게 매칭 허용 오차 (g)
            get_product_weight: product_id -> weight 조회 함수 (없으면 aggregated에서 조회)
        """
        self._weight_tolerance = weight_tolerance
        self._get_product_weight = get_product_weight

    def aggregate(
        self,
        triggers: List[TriggerResult],
    ) -> Dict[int, AggregatedProduct]:
        """
        여러 TriggerResult의 상품을 통합.

        합산 로직:
        1. 제거(delta<0): 상품 count 증가 (YOLO 결과 사용)
        2. 반환(delta>0): 무게 매칭하여 count 감소

        Args:
            triggers: TriggerResult 목록 (시간순)

        Returns:
            통합된 상품 결과 (product_id -> AggregatedProduct)
        """
        aggregated: Dict[int, AggregatedProduct] = {}

        for trigger in triggers:
            if trigger.is_return:
                # 반환 처리: 무게 매칭하여 차감
                self._handle_return(aggregated, trigger.delta_weight)
            else:
                # 제거 처리: YOLO 결과 합산
                self._handle_removal(aggregated, trigger)

        logger.debug(
            f"Aggregated {len(triggers)} triggers -> {len(aggregated)} products, "
            f"total count={sum(p.count for p in aggregated.values())}"
        )

        return aggregated

    def _handle_removal(
        self,
        aggregated: Dict[int, AggregatedProduct],
        trigger: TriggerResult,
    ) -> None:
        """
        제거 처리: YOLO 결과 합산.

        Args:
            aggregated: 통합 상품 딕셔너리 (in-place 수정)
            trigger: 제거 trigger 결과
        """
        for product in trigger.products:
            if product.count <= 0:
                continue

            product_id = product.product_id

            if product_id in aggregated:
                # 기존 상품에 합산
                agg = aggregated[product_id]
                agg.count += product.count
                agg.total_confidence += product.confidence * product.count
                agg.detection_count += product.count
            else:
                # 새 상품 추가
                aggregated[product_id] = AggregatedProduct(
                    product_id=product_id,
                    product_idx=product.product_idx,
                    name=product.name,
                    count=product.count,
                    unit_price=product.price,
                    weight=self._get_weight_for_product(product),
                    total_confidence=product.confidence * product.count,
                    detection_count=product.count,
                )

            logger.debug(
                f"Added product: {product.name} x{product.count} "
                f"(id={product_id}, total={aggregated[product_id].count})"
            )

    def _handle_return(
        self,
        aggregated: Dict[int, AggregatedProduct],
        delta_weight: float,
    ) -> Optional[int]:
        """
        반환 처리: 무게 매칭하여 차감.

        무게 증가(delta > 0) 시 반환 처리.
        매칭되는 상품의 count를 1 감소시킵니다.

        예시:
        - aggregated에 치킨마요(365g) x2, 김밥(250g) x1 있음
        - delta_weight = +363g 들어옴
        - 365g ± 3g = 362~368g 범위에 363g 포함
        - 치킨마요 count -= 1 → 치킨마요 x1 남음

        Args:
            aggregated: 통합 상품 딕셔너리 (in-place 수정)
            delta_weight: 무게 증가량 (양수)

        Returns:
            차감된 product_id 또는 None (매칭 실패)
        """
        if delta_weight <= 0:
            return None

        # 무게로 상품 찾기
        matched_product_id = self.find_product_by_weight(aggregated, delta_weight)

        if matched_product_id is not None:
            agg = aggregated[matched_product_id]
            if agg.count > 0:
                agg.count = max(0, agg.count - 1)  # 음수 방지
                logger.info(
                    f"Return processed: {agg.name} "
                    f"(weight match: {delta_weight:.1f}g ~ {agg.weight:.1f}g, "
                    f"remaining count={agg.count})"
                )
                return matched_product_id

        logger.warning(
            f"Return weight matching failed: {delta_weight:.1f}g "
            f"(tolerance={self._weight_tolerance}g)"
        )
        return None

    def find_product_by_weight(
        self,
        aggregated: Dict[int, AggregatedProduct],
        weight: float,
    ) -> Optional[int]:
        """
        무게로 상품 찾기.

        허용 오차 내에서 가장 가까운 무게의 상품을 찾습니다.
        count > 0인 상품만 대상으로 합니다.

        Args:
            aggregated: 통합 상품 딕셔너리
            weight: 찾을 무게 (g)

        Returns:
            매칭된 product_id 또는 None
        """
        best_match: Optional[int] = None
        best_diff = float("inf")

        for product_id, agg in aggregated.items():
            if agg.count <= 0:
                continue
            if agg.weight <= 0:
                continue

            diff = abs(agg.weight - weight)
            if diff <= self._weight_tolerance and diff < best_diff:
                best_diff = diff
                best_match = product_id

        if best_match is not None:
            logger.debug(
                f"Weight match found: {weight:.1f}g -> "
                f"product_id={best_match} (diff={best_diff:.1f}g)"
            )

        return best_match

    def _get_weight_for_product(self, product: ProductResult) -> float:
        """
        상품의 무게 조회.

        Args:
            product: 상품 결과

        Returns:
            무게 (g)
        """
        if self._get_product_weight is not None:
            weight = self._get_product_weight(product.product_id)
            if weight > 0:
                return weight

        # Fallback: ProductResult에는 무게 정보가 없으므로 0 반환
        # DoorSessionStore에서 product_db를 통해 설정해야 함
        return 0.0

    def update_weights_from_db(
        self,
        aggregated: Dict[int, AggregatedProduct],
        get_weight: Callable[[int], float],
    ) -> int:
        """
        ProductDatabase에서 무게 정보 업데이트.

        Args:
            aggregated: 통합 상품 딕셔너리 (in-place 수정)
            get_weight: product_id -> weight 조회 함수

        Returns:
            업데이트된 상품 수
        """
        updated = 0
        for product_id, agg in aggregated.items():
            if agg.weight <= 0:
                weight = get_weight(product_id)
                if weight > 0:
                    agg.weight = weight
                    updated += 1
        return updated
