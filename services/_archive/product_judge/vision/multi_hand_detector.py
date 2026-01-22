"""
Multi-Hand Detector.

최대 6개 손 (3명 × 2손) 동시 감지 및 클러스터링.

핵심 기능:
1. 다중 손 감지 및 그룹화 (같은 사람)
2. 각 손/손 그룹별 최근접 상품 할당
3. 다중 사용자 동시 취출 지원 (시나리오 4)

사용 예시:
    detector = MultiHandDetector(max_distance_px=150.0)
    hand_clusters = detector.detect_hand_clusters(detections)
    assignments = detector.assign_products_to_hands(hand_clusters, products)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import logging

from .yolo_wrapper import YOLODetection

logger = logging.getLogger(__name__)


@dataclass
class HandCluster:
    """
    손 클러스터 (같은 사람의 손들).

    Attributes:
        cluster_id: 클러스터 ID
        hands: 손 Detection 리스트 (1~2개)
        center: 클러스터 중심점
        assigned_products: 할당된 상품 리스트
    """
    cluster_id: int
    hands: List[YOLODetection] = field(default_factory=list)
    assigned_products: List[YOLODetection] = field(default_factory=list)

    @property
    def center(self) -> Tuple[float, float]:
        """클러스터 중심점."""
        if not self.hands:
            return (0.0, 0.0)

        cx = sum(h.center_x for h in self.hands) / len(self.hands)
        cy = sum(h.center_y for h in self.hands) / len(self.hands)
        return (cx, cy)

    @property
    def primary_hand(self) -> Optional[YOLODetection]:
        """대표 손 (confidence 가장 높은 손)."""
        if not self.hands:
            return None
        return max(self.hands, key=lambda h: h.conf)

    @property
    def hand_count(self) -> int:
        """손 개수."""
        return len(self.hands)

    @property
    def avg_confidence(self) -> float:
        """평균 confidence."""
        if not self.hands:
            return 0.0
        return sum(h.conf for h in self.hands) / len(self.hands)

    def distance_to_point(self, x: float, y: float) -> float:
        """특정 점과의 거리."""
        cx, cy = self.center
        return ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5

    def distance_to_detection(self, detection: YOLODetection) -> float:
        """Detection과의 최소 거리 (가장 가까운 손 기준)."""
        if not self.hands:
            return float('inf')

        return min(h.distance_to(detection) for h in self.hands)

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "cluster_id": self.cluster_id,
            "hand_count": self.hand_count,
            "center": list(self.center),
            "avg_confidence": round(self.avg_confidence, 3),
            "hands": [h.to_dict() for h in self.hands],
            "assigned_products": [p.to_dict() for p in self.assigned_products],
        }


@dataclass
class MultiHandFilterResult:
    """
    다중 손 필터링 결과.

    Attributes:
        hand_clusters: 손 클러스터 리스트
        all_hands: 모든 손
        all_products: 모든 상품
        assigned_products: 할당된 상품들 (중복 제거)
        unassigned_products: 미할당 상품들
    """
    hand_clusters: List[HandCluster]
    all_hands: List[YOLODetection]
    all_products: List[YOLODetection]
    assigned_products: List[YOLODetection] = field(default_factory=list)
    unassigned_products: List[YOLODetection] = field(default_factory=list)

    @property
    def person_count(self) -> int:
        """추정 인원 수 (클러스터 수)."""
        return len(self.hand_clusters)

    @property
    def total_hands(self) -> int:
        """총 손 개수."""
        return len(self.all_hands)

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "person_count": self.person_count,
            "total_hands": self.total_hands,
            "clusters": [c.to_dict() for c in self.hand_clusters],
            "assigned_count": len(self.assigned_products),
            "unassigned_count": len(self.unassigned_products),
        }


class MultiHandDetector:
    """
    다중 손 감지기.

    여러 손을 감지하고 클러스터링하여 각각에 상품을 할당합니다.

    Attributes:
        max_distance_px: 손-상품 최대 거리 (픽셀)
        hand_cluster_distance: 같은 사람의 손 클러스터링 거리 (픽셀)
        hand_class_id: 손 클래스 ID
        max_products_per_hand: 손당 최대 할당 상품 수
    """

    def __init__(
        self,
        max_distance_px: float = 150.0,
        hand_cluster_distance: float = 200.0,
        hand_class_id: int = 0,
        max_products_per_hand: int = 3,
    ):
        """
        감지기 초기화.

        Args:
            max_distance_px: 손-상품 최대 거리 (픽셀)
            hand_cluster_distance: 손 클러스터링 거리 (픽셀)
            hand_class_id: 손 클래스 ID
            max_products_per_hand: 손당 최대 할당 상품 수
        """
        self.max_distance_px = max_distance_px
        self.hand_cluster_distance = hand_cluster_distance
        self.hand_class_id = hand_class_id
        self.max_products_per_hand = max_products_per_hand

    def detect_hand_clusters(
        self,
        detections: List[YOLODetection],
    ) -> List[HandCluster]:
        """
        손 감지 및 클러스터링.

        가까운 손들을 같은 사람으로 그룹화합니다.

        Args:
            detections: YOLO 감지 결과

        Returns:
            HandCluster 리스트
        """
        # 손 분리
        hands = [d for d in detections if d.cls == self.hand_class_id]

        if not hands:
            return []

        # 클러스터링 (Union-Find 스타일)
        clusters: List[HandCluster] = []
        used = set()

        for i, hand in enumerate(hands):
            if i in used:
                continue

            # 새 클러스터 시작
            cluster = HandCluster(cluster_id=len(clusters))
            cluster.hands.append(hand)
            used.add(i)

            # 가까운 손 찾기
            for j, other_hand in enumerate(hands):
                if j in used:
                    continue

                distance = hand.distance_to(other_hand)
                if distance <= self.hand_cluster_distance:
                    cluster.hands.append(other_hand)
                    used.add(j)

            clusters.append(cluster)

        logger.debug(
            f"Clustered {len(hands)} hands into {len(clusters)} clusters"
        )

        return clusters

    def assign_products_to_hands(
        self,
        hand_clusters: List[HandCluster],
        products: List[YOLODetection],
    ) -> Dict[int, List[YOLODetection]]:
        """
        각 손 클러스터에 근접 상품 매핑.

        Args:
            hand_clusters: 손 클러스터 리스트
            products: 상품 Detection 리스트

        Returns:
            {cluster_id: [products]} 매핑
        """
        assignments: Dict[int, List[YOLODetection]] = {
            c.cluster_id: [] for c in hand_clusters
        }

        # 상품 할당 상태
        product_assigned = {id(p): False for p in products}

        for cluster in hand_clusters:
            # 각 상품과의 거리 계산
            product_distances: List[Tuple[YOLODetection, float]] = []

            for product in products:
                if product_assigned[id(product)]:
                    continue

                distance = cluster.distance_to_detection(product)
                if distance <= self.max_distance_px:
                    product_distances.append((product, distance))

            # 거리순 정렬
            product_distances.sort(key=lambda x: x[1])

            # 최대 N개까지 할당
            for product, distance in product_distances[:self.max_products_per_hand]:
                cluster.assigned_products.append(product)
                assignments[cluster.cluster_id].append(product)
                product_assigned[id(product)] = True

                logger.debug(
                    f"Assigned {product.name} to cluster {cluster.cluster_id} "
                    f"(distance={distance:.1f}px)"
                )

        return assignments

    def filter(
        self,
        detections: List[YOLODetection],
    ) -> MultiHandFilterResult:
        """
        다중 손 필터링 (전체 파이프라인).

        Args:
            detections: YOLO 감지 결과

        Returns:
            MultiHandFilterResult
        """
        # 손/상품 분리
        hands = [d for d in detections if d.cls == self.hand_class_id]
        products = [d for d in detections if d.cls != self.hand_class_id]

        logger.debug(f"Input: {len(hands)} hands, {len(products)} products")

        # 손이 없으면 모든 상품 반환
        if not hands:
            logger.info("No hands detected, returning all products")
            return MultiHandFilterResult(
                hand_clusters=[],
                all_hands=[],
                all_products=products,
                assigned_products=products,
                unassigned_products=[],
            )

        # 클러스터링
        clusters = self.detect_hand_clusters(detections)

        # 상품 할당
        self.assign_products_to_hands(clusters, products)

        # 할당된/미할당 상품 수집
        assigned = []
        for cluster in clusters:
            assigned.extend(cluster.assigned_products)

        assigned_ids = {id(p) for p in assigned}
        unassigned = [p for p in products if id(p) not in assigned_ids]

        logger.info(
            f"Multi-hand filter: {len(clusters)} persons, "
            f"{len(assigned)} assigned, {len(unassigned)} unassigned products"
        )

        return MultiHandFilterResult(
            hand_clusters=clusters,
            all_hands=hands,
            all_products=products,
            assigned_products=assigned,
            unassigned_products=unassigned,
        )

    def filter_for_zone(
        self,
        detections: List[YOLODetection],
        zone_y_ranges: Optional[Dict[int, Tuple[float, float]]] = None,
    ) -> Dict[int, MultiHandFilterResult]:
        """
        Zone별 다중 손 필터링.

        각 Zone의 y 좌표 범위를 기준으로 손과 상품을 분리합니다.

        Args:
            detections: YOLO 감지 결과
            zone_y_ranges: {zone_id: (y_min, y_max)} 매핑

        Returns:
            {zone_id: MultiHandFilterResult} 매핑
        """
        if not zone_y_ranges:
            # 기본 5개 Zone (y좌표 기준 균등 분할)
            # 예: 이미지 높이 480px 기준
            zone_y_ranges = {
                0: (0, 96),
                1: (96, 192),
                2: (192, 288),
                3: (288, 384),
                4: (384, 480),
            }

        results: Dict[int, MultiHandFilterResult] = {}

        for zone_id, (y_min, y_max) in zone_y_ranges.items():
            # Zone 내 detection 필터링
            zone_detections = [
                d for d in detections
                if y_min <= d.center_y < y_max
            ]

            if zone_detections:
                results[zone_id] = self.filter(zone_detections)
            else:
                results[zone_id] = MultiHandFilterResult(
                    hand_clusters=[],
                    all_hands=[],
                    all_products=[],
                )

        return results

    def get_nearest_products_per_person(
        self,
        detections: List[YOLODetection],
        top_k: int = 5,
    ) -> Dict[int, List[YOLODetection]]:
        """
        각 사람(클러스터)별 Top-K 상품 추출.

        Args:
            detections: YOLO 감지 결과
            top_k: 추출할 상품 수

        Returns:
            {cluster_id: [Top-K products]} 매핑
        """
        result = self.filter(detections)

        person_products: Dict[int, List[YOLODetection]] = {}

        for cluster in result.hand_clusters:
            # confidence 기준 정렬
            sorted_products = sorted(
                cluster.assigned_products,
                key=lambda p: p.conf,
                reverse=True,
            )
            person_products[cluster.cluster_id] = sorted_products[:top_k]

        return person_products
