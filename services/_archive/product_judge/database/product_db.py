"""
Product Database for Product Judgment Service.

상품 정보(이름, 무게, 가격) 관리.

지원 형식:
- YAML 파일 로드
- 딕셔너리 직접 초기화
- 50개 기본 상품 내장

사용 예시:
    db = ProductDatabase.from_yaml("products.yaml")
    product = db.get_product(1)
    price = db.get_price(1)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from ..engine.models import ProductInfo

logger = logging.getLogger(__name__)


# 기본 50개 상품 데이터
DEFAULT_PRODUCTS: List[Dict] = [
    # class_id 0 = hand (비상품)
    {"id": 0, "name": "hand", "category": "non_product", "weight": 0, "price": 0},

    # 음료 (1-10)
    {"id": 1, "name": "pulmuone_spring_water_500", "category": "beverage", "weight": 520, "price": 1200},
    {"id": 2, "name": "samdasoo_500", "category": "beverage", "weight": 520, "price": 1000},
    {"id": 3, "name": "evian_500", "category": "beverage", "weight": 530, "price": 2500},
    {"id": 4, "name": "coca_cola_350", "category": "beverage", "weight": 380, "price": 1800},
    {"id": 5, "name": "sprite_350", "category": "beverage", "weight": 380, "price": 1800},
    {"id": 6, "name": "fanta_orange_350", "category": "beverage", "weight": 385, "price": 1800},
    {"id": 7, "name": "pocari_sweat_500", "category": "beverage", "weight": 540, "price": 2000},
    {"id": 8, "name": "gatorade_600", "category": "beverage", "weight": 640, "price": 2500},
    {"id": 9, "name": "vita500", "category": "beverage", "weight": 130, "price": 1200},
    {"id": 10, "name": "hot6", "category": "beverage", "weight": 260, "price": 1500},

    # 스낵 (11-20)
    {"id": 11, "name": "pepero_original", "category": "snack", "weight": 69, "price": 1500},
    {"id": 12, "name": "pepero_almond", "category": "snack", "weight": 72, "price": 1700},
    {"id": 13, "name": "choco_pie", "category": "snack", "weight": 39, "price": 800},
    {"id": 14, "name": "orion_pie", "category": "snack", "weight": 35, "price": 700},
    {"id": 15, "name": "honey_butter_chip", "category": "snack", "weight": 60, "price": 2000},
    {"id": 16, "name": "potato_chip_original", "category": "snack", "weight": 65, "price": 1800},
    {"id": 17, "name": "shrimp_chip", "category": "snack", "weight": 90, "price": 1500},
    {"id": 18, "name": "onion_ring", "category": "snack", "weight": 84, "price": 1600},
    {"id": 19, "name": "cheese_ball", "category": "snack", "weight": 70, "price": 1400},
    {"id": 20, "name": "pringles_original", "category": "snack", "weight": 53, "price": 2500},

    # 초콜릿/캔디 (21-25)
    {"id": 21, "name": "snickers", "category": "candy", "weight": 52, "price": 1500},
    {"id": 22, "name": "twix", "category": "candy", "weight": 50, "price": 1500},
    {"id": 23, "name": "kitkat", "category": "candy", "weight": 45, "price": 1200},
    {"id": 24, "name": "m_and_m", "category": "candy", "weight": 45, "price": 2000},
    {"id": 25, "name": "ferrero_rocher", "category": "candy", "weight": 37, "price": 2500},

    # 편의점 식품 (26-35)
    {"id": 26, "name": "chickenmayo_rice", "category": "food", "weight": 365, "price": 3500},
    {"id": 27, "name": "tuna_rice", "category": "food", "weight": 350, "price": 3200},
    {"id": 28, "name": "spam_rice", "category": "food", "weight": 380, "price": 3800},
    {"id": 29, "name": "egg_sandwich", "category": "food", "weight": 170, "price": 2800},
    {"id": 30, "name": "ham_sandwich", "category": "food", "weight": 180, "price": 3200},
    {"id": 31, "name": "tuna_sandwich", "category": "food", "weight": 175, "price": 3500},
    {"id": 32, "name": "cup_noodle_small", "category": "food", "weight": 65, "price": 1200},
    {"id": 33, "name": "cup_noodle_big", "category": "food", "weight": 110, "price": 1800},
    {"id": 34, "name": "instant_rice", "category": "food", "weight": 210, "price": 2000},
    {"id": 35, "name": "kimbap", "category": "food", "weight": 250, "price": 2500},

    # 유제품 (36-42)
    {"id": 36, "name": "seoul_milk_200", "category": "dairy", "weight": 210, "price": 1200},
    {"id": 37, "name": "banana_milk", "category": "dairy", "weight": 245, "price": 1500},
    {"id": 38, "name": "strawberry_milk", "category": "dairy", "weight": 245, "price": 1500},
    {"id": 39, "name": "chocolate_milk", "category": "dairy", "weight": 250, "price": 1500},
    {"id": 40, "name": "yogurt_plain", "category": "dairy", "weight": 85, "price": 1000},
    {"id": 41, "name": "yogurt_strawberry", "category": "dairy", "weight": 90, "price": 1200},
    {"id": 42, "name": "cheese_slice_pack", "category": "dairy", "weight": 200, "price": 3500},

    # 건강식품 (43-47)
    {"id": 43, "name": "protein_bar", "category": "health", "weight": 50, "price": 2500},
    {"id": 44, "name": "energy_bar", "category": "health", "weight": 45, "price": 2000},
    {"id": 45, "name": "granola_bar", "category": "health", "weight": 40, "price": 1800},
    {"id": 46, "name": "vitamin_c", "category": "health", "weight": 35, "price": 1500},
    {"id": 47, "name": "multivitamin", "category": "health", "weight": 30, "price": 2000},

    # 기타 (48-50)
    {"id": 48, "name": "gum_pack", "category": "etc", "weight": 25, "price": 1000},
    {"id": 49, "name": "mint_candy", "category": "etc", "weight": 15, "price": 800},
    {"id": 50, "name": "wet_tissue", "category": "etc", "weight": 50, "price": 1000},
]


class ProductDatabase:
    """
    상품 정보 데이터베이스.

    상품 ID → 상품 정보(이름, 무게, 가격) 매핑.

    Attributes:
        _products: {product_id: ProductInfo} 딕셔너리
    """

    def __init__(self, products: Optional[List[Dict]] = None):
        """
        데이터베이스 초기화.

        Args:
            products: 상품 정보 리스트. None이면 기본 50개 상품 사용.
        """
        self._products: Dict[int, ProductInfo] = {}

        if products is None:
            products = DEFAULT_PRODUCTS

        for p in products:
            product = ProductInfo(
                product_id=p["id"],
                name=p["name"],
                category=p.get("category", "unknown"),
                weight=float(p["weight"]),
                price=int(p.get("price", 0)),
            )
            self._products[product.product_id] = product

        logger.info(f"ProductDatabase initialized with {len(self._products)} products")

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ProductDatabase":
        """
        YAML 파일에서 데이터베이스 생성.

        Args:
            yaml_path: YAML 파일 경로

        Returns:
            ProductDatabase 인스턴스

        Raises:
            ImportError: PyYAML이 설치되지 않음
            FileNotFoundError: YAML 파일을 찾을 수 없음
        """
        if not HAS_YAML:
            raise ImportError("PyYAML is required to load YAML files. Install with: pip install pyyaml")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # classes 키가 있으면 그것을 사용, 아니면 전체 데이터가 리스트라고 가정
        if isinstance(data, dict) and "classes" in data:
            products = data["classes"]
        elif isinstance(data, list):
            products = data
        else:
            raise ValueError(f"Invalid YAML format: expected 'classes' key or list, got {type(data)}")

        return cls(products)

    def get_product(self, product_id: int) -> Optional[ProductInfo]:
        """
        상품 정보 조회.

        Args:
            product_id: 상품 ID

        Returns:
            ProductInfo 또는 None
        """
        return self._products.get(product_id)

    def get_weight(self, product_id: int) -> float:
        """
        상품 무게 조회.

        Args:
            product_id: 상품 ID

        Returns:
            무게 (g). 없으면 0.0
        """
        product = self.get_product(product_id)
        return product.weight if product else 0.0

    def get_price(self, product_id: int) -> int:
        """
        상품 가격 조회.

        Args:
            product_id: 상품 ID

        Returns:
            가격 (원). 없으면 0
        """
        product = self.get_product(product_id)
        return product.price if product else 0

    def get_name(self, product_id: int) -> str:
        """
        상품 이름 조회.

        Args:
            product_id: 상품 ID

        Returns:
            이름. 없으면 "unknown"
        """
        product = self.get_product(product_id)
        return product.name if product else "unknown"

    def get_category(self, product_id: int) -> str:
        """
        상품 카테고리 조회.

        Args:
            product_id: 상품 ID

        Returns:
            카테고리. 없으면 "unknown"
        """
        product = self.get_product(product_id)
        return product.category if product else "unknown"

    def get_tolerance(self, product_id: int, default: float = 0.10) -> float:
        """
        상품 카테고리별 허용 오차 조회.

        Args:
            product_id: 상품 ID
            default: 기본 허용 오차

        Returns:
            허용 오차 (0.0 ~ 1.0)
        """
        category = self.get_category(product_id)
        tolerances = {
            "beverage": 0.05,   # 5%
            "snack": 0.10,      # 10%
            "candy": 0.10,      # 10%
            "food": 0.08,       # 8%
            "dairy": 0.07,      # 7%
            "health": 0.10,     # 10%
            "frozen": 0.15,     # 15% (결빙으로 인한 무게 변동)
            "etc": 0.15,        # 15%
        }
        return tolerances.get(category, default)

    def search_by_weight(
        self,
        target_weight: float,
        tolerance: float = 0.15,
        exclude_hand: bool = True,
    ) -> List[ProductInfo]:
        """
        무게 범위로 상품 검색.

        Args:
            target_weight: 목표 무게 (g)
            tolerance: 허용 오차 비율 (0.0 ~ 1.0)
            exclude_hand: hand (class_id=0) 제외 여부

        Returns:
            매칭되는 상품 리스트
        """
        matches = []
        min_weight = target_weight * (1 - tolerance)
        max_weight = target_weight * (1 + tolerance)

        for product in self._products.values():
            if exclude_hand and product.product_id == 0:
                continue
            if product.weight <= 0:
                continue
            if min_weight <= product.weight <= max_weight:
                matches.append(product)

        return matches

    def get_all_products(self, exclude_hand: bool = True) -> List[ProductInfo]:
        """
        모든 상품 조회.

        Args:
            exclude_hand: hand (class_id=0) 제외 여부

        Returns:
            상품 리스트
        """
        if exclude_hand:
            return [p for p in self._products.values() if p.product_id != 0]
        return list(self._products.values())

    @property
    def product_count(self) -> int:
        """등록된 상품 수 (hand 제외)."""
        return len([p for p in self._products.values() if p.product_id != 0])

    def __len__(self) -> int:
        """전체 항목 수."""
        return len(self._products)

    def __contains__(self, product_id: int) -> bool:
        """상품 ID 존재 여부."""
        return product_id in self._products

    def to_dict(self) -> Dict[int, dict]:
        """딕셔너리 형태로 변환."""
        return {pid: p.to_dict() for pid, p in self._products.items()}
