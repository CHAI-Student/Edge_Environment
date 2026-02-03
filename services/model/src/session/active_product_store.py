"""
Active Product Store (v4.4).

Node.js에서 받은 활성 상품 정보를 zone별로 임시 관리.
YOLO classes 파라미터를 통한 사전 필터링 지원.

핵심 기능:
- Node.js products 배열에서 YOLO class_id 추출
- stock_qty > 0 상품만 allowed_class_ids에 포함
- 문 닫힘(finalize) 시 자동 정리

사용법:
    store = ActiveProductStore(yolo_mapping=yolo_mapping_dict)

    # products 설정 (Node.js 폴링 시)
    result = store.set_products(zone=1, products=products_list)

    # YOLO 추론 전 허용 클래스 조회
    allowed_ids = store.get_allowed_class_ids(zone=1)

    # 문 닫힘 시 정리
    store.clear(zone=1)
"""

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProductInfo:
    """Node.js에서 받은 상품 정보."""

    product_idx: str
    product_name: str
    sale_price: int
    product_weight: float
    stock_qty: int
    yolo_class_id: Optional[int] = None  # 매핑된 YOLO 클래스 ID


@dataclass
class ZoneData:
    """Zone별 상품 데이터."""

    products: List[ProductInfo]  # Node.js 원본 (매핑 성공한 것만)
    allowed_class_ids: List[int]  # YOLO 허용 클래스 IDs (stock > 0)
    class_to_product: Dict[int, ProductInfo]  # class_id -> ProductInfo 빠른 조회
    updated_at: float = field(default_factory=time.time)


@dataclass
class SetProductsResult:
    """set_products() 결과."""

    success: bool
    zone: int
    total_products: int  # Node.js에서 받은 총 상품 수
    mapped_products: int  # YOLO 매핑 성공한 상품 수
    allowed_products: int  # stock > 0인 상품 수 (allowed_class_ids 개수)
    unmapped_names: List[str]  # 매핑 실패한 상품명 목록


class ActiveProductStore:
    """
    Node.js에서 받은 활성 상품 정보를 zone별로 임시 관리.

    YOLO classes 파라미터를 통한 사전 필터링 지원.
    yolo_product_mapping.json에서 로드된 매핑 정보를 사용하여
    product_name → yolo_class_id 변환.

    Thread-safe: 내부 Lock 사용.
    """

    def __init__(
        self,
        yolo_name_to_id: Optional[Dict[str, int]] = None,
    ):
        """
        Initialize ActiveProductStore.

        Args:
            yolo_name_to_id: {yolo_class_name: yolo_class_id} 매핑
                             yolo_product_mapping.json에서 로드
        """
        self._yolo_name_to_id: Dict[str, int] = yolo_name_to_id or {}
        self._yolo_name_normalized: Dict[str, int] = {}  # 정규화된 이름 매핑
        self._zones: Dict[int, ZoneData] = {}
        self._lock = threading.Lock()

        # 정규화된 이름 매핑 생성
        self._build_normalized_mapping()

        logger.info(
            f"ActiveProductStore initialized: "
            f"{len(self._yolo_name_to_id)} YOLO classes"
        )

    def _build_normalized_mapping(self) -> None:
        """정규화된 이름 매핑 생성."""
        for name, class_id in self._yolo_name_to_id.items():
            normalized = self._normalize_name(name)
            self._yolo_name_normalized[normalized] = class_id

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        상품명 정규화.

        밑줄, 공백, 하이픈 등 제거하고 대문자로 변환.

        Args:
            name: 상품명

        Returns:
            정규화된 이름
        """
        # 밑줄, 하이픈, 공백, 점, 슬래시 등 제거
        normalized = re.sub(r'[_\-\.\s\/\\]', '', name)
        return normalized.upper()

    def load_yolo_mapping(self, mapping_data: dict) -> int:
        """
        yolo_product_mapping.json 데이터 로드.

        Args:
            mapping_data: {"mappings": [{"yolo_class_id": 1, "yolo_class_name": "..."}, ...]}

        Returns:
            로드된 매핑 수
        """
        mappings = mapping_data.get("mappings", [])
        count = 0

        for m in mappings:
            yolo_class_id = m.get("yolo_class_id")
            yolo_class_name = m.get("yolo_class_name")

            if yolo_class_id is None or not yolo_class_name:
                continue

            self._yolo_name_to_id[yolo_class_name] = yolo_class_id
            normalized = self._normalize_name(yolo_class_name)
            self._yolo_name_normalized[normalized] = yolo_class_id
            count += 1

        logger.info(f"Loaded {count} YOLO class mappings")
        return count

    def _find_yolo_class_id(self, product_name: str) -> Optional[int]:
        """
        상품명으로 YOLO class_id 찾기.

        매칭 순서:
        1. 정확한 이름 매칭 (대소문자 무시)
        2. 정규화 후 매칭 (밑줄/공백 무시)

        Args:
            product_name: Node.js에서 받은 상품명

        Returns:
            YOLO class_id 또는 None
        """
        if not product_name:
            return None

        # 1. 정확한 이름 매칭 (대소문자 무시)
        name_upper = product_name.upper()
        for yolo_name, class_id in self._yolo_name_to_id.items():
            if yolo_name.upper() == name_upper:
                return class_id

        # 2. 정규화 후 매칭
        normalized = self._normalize_name(product_name)
        return self._yolo_name_normalized.get(normalized)

    def set_products(
        self,
        zone: int,
        products: List[dict],
    ) -> SetProductsResult:
        """
        Node.js 상품 리스트 저장.

        product_name → yolo_class_id 매핑 수행.
        stock_qty > 0인 상품만 allowed_class_ids에 추가.

        Args:
            zone: Zone 번호
            products: Node.js에서 받은 상품 리스트
                      [{"product_idx": "...", "product_name": "...",
                        "sale_price": 0, "product_weight": "0", "stock_qty": 0}, ...]

        Returns:
            SetProductsResult
        """
        mapped_products: List[ProductInfo] = []
        allowed_class_ids: List[int] = []
        class_to_product: Dict[int, ProductInfo] = {}
        unmapped_names: List[str] = []

        for p in products:
            product_name = p.get("product_name", "")
            product_idx = p.get("product_idx", "")
            sale_price = int(p.get("sale_price", 0))
            stock_qty = int(p.get("stock_qty", 0))

            # product_weight는 문자열일 수 있음
            weight_str = p.get("product_weight", "0")
            try:
                product_weight = float(weight_str) if weight_str else 0.0
            except (ValueError, TypeError):
                product_weight = 0.0

            # YOLO class_id 찾기
            yolo_class_id = self._find_yolo_class_id(product_name)

            if yolo_class_id is None:
                unmapped_names.append(product_name)
                continue

            # ProductInfo 생성
            product_info = ProductInfo(
                product_idx=product_idx,
                product_name=product_name,
                sale_price=sale_price,
                product_weight=product_weight,
                stock_qty=stock_qty,
                yolo_class_id=yolo_class_id,
            )
            mapped_products.append(product_info)
            class_to_product[yolo_class_id] = product_info

            # stock > 0이면 allowed_class_ids에 추가
            if stock_qty > 0:
                allowed_class_ids.append(yolo_class_id)

        # Zone 데이터 저장
        with self._lock:
            self._zones[zone] = ZoneData(
                products=mapped_products,
                allowed_class_ids=allowed_class_ids,
                class_to_product=class_to_product,
                updated_at=time.time(),
            )

        result = SetProductsResult(
            success=len(mapped_products) > 0,
            zone=zone,
            total_products=len(products),
            mapped_products=len(mapped_products),
            allowed_products=len(allowed_class_ids),
            unmapped_names=unmapped_names[:10],  # 최대 10개만 반환
        )

        logger.info(
            f"[ActiveProductStore] zone={zone}: "
            f"set {result.mapped_products}/{result.total_products} products, "
            f"allowed_classes={len(allowed_class_ids)}"
        )

        if unmapped_names:
            logger.warning(
                f"[ActiveProductStore] zone={zone}: "
                f"{len(unmapped_names)} unmapped products: {unmapped_names[:5]}"
            )

        return result

    def has_products(self, zone: int) -> bool:
        """
        해당 zone에 상품 정보가 있는지 확인.

        Args:
            zone: Zone 번호

        Returns:
            상품 정보 존재 여부
        """
        with self._lock:
            zone_data = self._zones.get(zone)
            return zone_data is not None and len(zone_data.products) > 0

    def get_allowed_class_ids(self, zone: int) -> Optional[List[int]]:
        """
        허용된 YOLO 클래스 ID 리스트.

        stock_qty > 0인 상품의 YOLO class_id만 반환.

        Args:
            zone: Zone 번호

        Returns:
            허용된 class_id 리스트.
            None이면 상품 정보가 없음 (YOLO 전체 클래스 탐지).
            빈 리스트면 허용된 상품이 없음 (모두 재고 0).
        """
        with self._lock:
            zone_data = self._zones.get(zone)
            if zone_data is None:
                return None
            return zone_data.allowed_class_ids.copy()

    def get_product_by_class_id(
        self,
        zone: int,
        class_id: int,
    ) -> Optional[ProductInfo]:
        """
        클래스 ID로 상품 정보 조회.

        Args:
            zone: Zone 번호
            class_id: YOLO class_id

        Returns:
            ProductInfo 또는 None
        """
        with self._lock:
            zone_data = self._zones.get(zone)
            if zone_data is None:
                return None
            return zone_data.class_to_product.get(class_id)

    def get_all_products(self, zone: int) -> List[ProductInfo]:
        """
        해당 zone의 모든 상품 정보 조회.

        Args:
            zone: Zone 번호

        Returns:
            ProductInfo 리스트 (빈 리스트면 없음)
        """
        with self._lock:
            zone_data = self._zones.get(zone)
            if zone_data is None:
                return []
            return zone_data.products.copy()

    def clear(self, zone: int) -> bool:
        """
        문 닫힘 시 해당 zone 데이터 삭제.

        Args:
            zone: Zone 번호

        Returns:
            삭제 성공 여부 (데이터가 있었으면 True)
        """
        with self._lock:
            if zone in self._zones:
                del self._zones[zone]
                logger.info(f"[ActiveProductStore] zone={zone}: cleared")
                return True
            return False

    def clear_all(self) -> int:
        """
        모든 zone 데이터 삭제.

        Returns:
            삭제된 zone 수
        """
        with self._lock:
            count = len(self._zones)
            self._zones.clear()
            if count > 0:
                logger.info(f"[ActiveProductStore] cleared all {count} zones")
            return count

    def get_stats(self) -> dict:
        """
        저장소 통계 반환.

        Returns:
            통계 정보
        """
        with self._lock:
            stats = {
                "total_yolo_classes": len(self._yolo_name_to_id),
                "active_zones": list(self._zones.keys()),
                "zone_count": len(self._zones),
                "zones": {},
            }

            for zone, zone_data in self._zones.items():
                stats["zones"][zone] = {
                    "products": len(zone_data.products),
                    "allowed_classes": len(zone_data.allowed_class_ids),
                    "updated_at": zone_data.updated_at,
                }

            return stats
