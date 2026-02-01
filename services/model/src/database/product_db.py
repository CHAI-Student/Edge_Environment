"""
Product Database for Model Service.

상품 정보(이름, 무게, 가격) 관리.

지원 형식:
- YAML 파일 로드
- JSON 파일 로드/저장 (영속화)
- 딕셔너리 직접 초기화
- 50개 기본 상품 내장

기능:
- 상품 등록/수정/삭제
- 무게/이름 기반 검색
- 바코드 지원 (선택)
- JSON 파일 영속화

사용 예시:
    db = ProductDatabase.from_yaml("products.yaml")
    product = db.get_product(1)
    price = db.get_price(1)

    # 상품 등록
    new_id = db.add_product("새우깡", "snack", 90, 1500, barcode="8801234567890")

    # 저장/로드
    db.save_to_file("products.json")
    db.load_from_file("products.json")
"""

from typing import Dict, List, Optional, Tuple
import logging
import json
import os
import re
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from engine.models import ProductInfo

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

    상품 ID -> 상품 정보(이름, 무게, 가격) 매핑.
    YOLO 클래스 ID와 IF11 상품 ID 간 매핑 지원.

    Attributes:
        _products: {product_id: ProductInfo} 딕셔너리
        _next_id: 다음 상품 ID
        _barcode_index: 바코드 -> product_id 인덱스
        _data_file: 영속화 파일 경로
        _yolo_to_product: yolo_class_id -> product_id 매핑
        _product_idx_to_id: product_idx -> product_id 매핑
        _yolo_name_to_id: yolo_class_name -> product_id 매핑
        _mapping_file: 매핑 파일 경로
    """

    def __init__(self, products: Optional[List[Dict]] = None, data_file: Optional[str] = None):
        """
        데이터베이스 초기화.

        Args:
            products: 상품 정보 리스트. None이면 기본 50개 상품 사용.
            data_file: 영속화 파일 경로 (자동 로드)
        """
        self._products: Dict[int, ProductInfo] = {}
        self._barcode_index: Dict[str, int] = {}  # barcode -> product_id
        self._data_file = data_file
        self._next_id = 51  # 기본 상품이 50개이므로 51부터 시작

        # YOLO-IF11 매핑 테이블
        self._yolo_to_product: Dict[int, int] = {}      # yolo_class_id -> product_id
        self._product_idx_to_id: Dict[str, int] = {}    # product_idx -> product_id
        self._yolo_name_to_id: Dict[str, int] = {}      # yolo_class_name -> product_id
        self._mapping_file: Optional[str] = None

        # 영속화 파일이 있으면 로드
        if data_file and os.path.exists(data_file):
            self.load_from_file(data_file)
            logger.info(f"ProductDatabase loaded from {data_file}")
        else:
            # 기본 상품 로드
            if products is None:
                products = DEFAULT_PRODUCTS

            for p in products:
                product = ProductInfo(
                    product_id=p["id"],
                    name=p["name"],
                    category=p.get("category", "unknown"),
                    weight=float(p["weight"]),
                    price=int(p.get("price", 0)),
                    barcode=p.get("barcode"),
                    stock=int(p.get("stock", 0)),
                    image_count=int(p.get("image_count", 0)),
                )
                self._products[product.product_id] = product
                if product.barcode:
                    self._barcode_index[product.barcode] = product.product_id

                # next_id 갱신
                if product.product_id >= self._next_id:
                    self._next_id = product.product_id + 1

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

    # =========================================================================
    # 상품 등록/수정/삭제
    # =========================================================================

    def add_product(
        self,
        name: str,
        category: str,
        weight: float,
        price: int,
        barcode: Optional[str] = None,
        stock: int = 0,
        product_id: Optional[int] = None,
    ) -> int:
        """
        새 상품 등록.

        Args:
            name: 상품 이름
            category: 카테고리 (beverage, snack, candy, food, dairy, health, etc)
            weight: 단위 무게 (g)
            price: 가격 (원)
            barcode: 바코드 (선택)
            stock: 초기 재고 (기본 0)
            product_id: 지정 ID (선택, None이면 자동 할당)

        Returns:
            등록된 상품 ID

        Raises:
            ValueError: 중복 바코드 또는 ID
        """
        # ID 결정
        if product_id is None:
            product_id = self._next_id
            self._next_id += 1
        elif product_id in self._products:
            raise ValueError(f"Product ID {product_id} already exists")

        # 바코드 중복 체크
        if barcode and barcode in self._barcode_index:
            raise ValueError(f"Barcode {barcode} already exists")

        # 상품 생성
        product = ProductInfo(
            product_id=product_id,
            name=name,
            category=category,
            weight=float(weight),
            price=int(price),
            barcode=barcode,
            stock=stock,
            image_count=0,
        )

        self._products[product_id] = product
        if barcode:
            self._barcode_index[barcode] = product_id

        # next_id 갱신
        if product_id >= self._next_id:
            self._next_id = product_id + 1

        logger.info(f"Product added: id={product_id}, name={name}")
        return product_id

    def update_product(
        self,
        product_id: int,
        name: Optional[str] = None,
        category: Optional[str] = None,
        weight: Optional[float] = None,
        price: Optional[int] = None,
        barcode: Optional[str] = None,
        stock: Optional[int] = None,
    ) -> bool:
        """
        상품 정보 수정.

        Args:
            product_id: 상품 ID
            name: 새 이름 (None이면 유지)
            category: 새 카테고리 (None이면 유지)
            weight: 새 무게 (None이면 유지)
            price: 새 가격 (None이면 유지)
            barcode: 새 바코드 (None이면 유지)
            stock: 새 재고 (None이면 유지)

        Returns:
            수정 성공 여부
        """
        if product_id not in self._products:
            logger.warning(f"Product {product_id} not found for update")
            return False

        product = self._products[product_id]

        # 바코드 변경 시 인덱스 갱신
        if barcode is not None and barcode != product.barcode:
            # 기존 바코드 제거
            if product.barcode and product.barcode in self._barcode_index:
                del self._barcode_index[product.barcode]
            # 새 바코드 중복 체크
            if barcode and barcode in self._barcode_index:
                raise ValueError(f"Barcode {barcode} already exists")
            # 새 바코드 등록
            if barcode:
                self._barcode_index[barcode] = product_id

        # 필드 업데이트 (dataclass는 frozen이 아니므로 직접 수정 가능)
        if name is not None:
            product.name = name
        if category is not None:
            product.category = category
        if weight is not None:
            product.weight = float(weight)
        if price is not None:
            product.price = int(price)
        if barcode is not None:
            product.barcode = barcode
        if stock is not None:
            product.stock = int(stock)

        logger.info(f"Product updated: id={product_id}")
        return True

    def delete_product(self, product_id: int) -> bool:
        """
        상품 삭제.

        Args:
            product_id: 상품 ID

        Returns:
            삭제 성공 여부
        """
        if product_id not in self._products:
            logger.warning(f"Product {product_id} not found for deletion")
            return False

        product = self._products[product_id]

        # 바코드 인덱스에서 제거
        if product.barcode and product.barcode in self._barcode_index:
            del self._barcode_index[product.barcode]

        del self._products[product_id]
        logger.info(f"Product deleted: id={product_id}")
        return True

    def increment_image_count(self, product_id: int, count: int = 1) -> bool:
        """
        상품 이미지 수 증가.

        Args:
            product_id: 상품 ID
            count: 증가량 (기본 1)

        Returns:
            성공 여부
        """
        if product_id not in self._products:
            return False
        self._products[product_id].image_count += count
        return True

    # =========================================================================
    # 검색
    # =========================================================================

    def get_by_barcode(self, barcode: str) -> Optional[ProductInfo]:
        """
        바코드로 상품 조회.

        Args:
            barcode: 바코드

        Returns:
            ProductInfo 또는 None
        """
        product_id = self._barcode_index.get(barcode)
        if product_id is not None:
            return self._products.get(product_id)
        return None

    def search_by_name(self, query: str, limit: int = 10) -> List[ProductInfo]:
        """
        이름으로 상품 검색 (부분 일치).

        Args:
            query: 검색어
            limit: 최대 결과 수

        Returns:
            매칭되는 상품 리스트
        """
        query_lower = query.lower()
        matches = []

        for product in self._products.values():
            if product.product_id == 0:  # hand 제외
                continue
            if query_lower in product.name.lower():
                matches.append(product)
                if len(matches) >= limit:
                    break

        return matches

    # =========================================================================
    # 영속화 (JSON)
    # =========================================================================

    def save_to_file(self, path: Optional[str] = None) -> None:
        """
        데이터베이스를 JSON 파일로 저장.

        Args:
            path: 파일 경로 (None이면 초기화 시 지정된 경로 사용)
        """
        save_path = path or self._data_file
        if not save_path:
            raise ValueError("No save path specified")

        # 디렉토리 생성
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "next_id": self._next_id,
            "products": [
                {
                    "id": p.product_id,
                    "name": p.name,
                    "category": p.category,
                    "weight": p.weight,
                    "price": p.price,
                    "barcode": p.barcode,
                    "stock": p.stock,
                    "image_count": p.image_count,
                }
                for p in self._products.values()
            ],
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"ProductDatabase saved to {save_path}")

    def load_from_file(self, path: Optional[str] = None) -> None:
        """
        JSON 파일에서 데이터베이스 로드.

        Args:
            path: 파일 경로 (None이면 초기화 시 지정된 경로 사용)
        """
        load_path = path or self._data_file
        if not load_path:
            raise ValueError("No load path specified")

        with open(load_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 기존 데이터 클리어
        self._products.clear()
        self._barcode_index.clear()

        # 버전 체크 (향후 마이그레이션용)
        version = data.get("version", "1.0")
        self._next_id = data.get("next_id", 51)

        # 상품 로드
        for p in data.get("products", []):
            product = ProductInfo(
                product_id=p["id"],
                name=p["name"],
                category=p.get("category", "unknown"),
                weight=float(p["weight"]),
                price=int(p.get("price", 0)),
                barcode=p.get("barcode"),
                stock=int(p.get("stock", 0)),
                image_count=int(p.get("image_count", 0)),
            )
            self._products[product.product_id] = product
            if product.barcode:
                self._barcode_index[product.barcode] = product.product_id

        logger.info(f"ProductDatabase loaded from {load_path}: {len(self._products)} products")

    # =========================================================================
    # Node.js 연동 (IF11 Import/Export)
    # =========================================================================

    def load_from_if11(self, product_list: List[dict]) -> int:
        """
        IF11 상품 리스트 형식에서 데이터베이스 갱신.

        Node.js로부터 받은 IF11 형식의 상품 리스트를 로드합니다.
        기존 상품은 업데이트하고, 새 상품은 추가합니다.
        YOLO 클래스와 자동 매칭도 시도합니다.

        IF11 형식:
            {
                "product_idx": "P17355176364813008",
                "product_name": "페리에 330ml",
                "sale_price": 1985,
                "stock_qty": 12,
                "product_weight": "550"  # 문자열 주의
            }

        Args:
            product_list: IF11 형식의 상품 리스트

        Returns:
            로드된 상품 수
        """
        loaded_count = 0

        for item in product_list:
            try:
                # IF11 필드 추출 (문자열 → 숫자 변환)
                product_idx = item.get("product_idx", "")
                name = item.get("product_name", "unknown")
                price = int(item.get("sale_price", 0))
                stock = int(item.get("stock_qty", 0))

                # product_weight는 문자열일 수 있음
                weight_str = item.get("product_weight", "0")
                weight = float(weight_str) if weight_str else 0.0

                # product_idx로 이미 등록된 상품이 있는지 확인
                existing_by_idx = self.get_by_product_idx(product_idx)
                if existing_by_idx:
                    # 기존 상품 업데이트
                    self.update_product(
                        product_id=existing_by_idx.product_id,
                        name=name,
                        price=price,
                        weight=weight,
                        stock=stock,
                    )
                    loaded_count += 1
                    continue

                # product_idx에서 숫자 ID 추출 시도 (예: "P17355176364813008" → 해시)
                # 간단히 인덱스 기반 ID 할당
                product_id = self._get_or_create_id_for_idx(product_idx)

                # 상품이 이미 존재하면 업데이트
                if product_id in self._products:
                    product = self._products[product_id]
                    self.update_product(
                        product_id=product_id,
                        name=name,
                        price=price,
                        weight=weight,
                        stock=stock,
                    )
                    # product_idx 설정
                    product.product_idx = product_idx
                    self._product_idx_to_id[product_idx] = product_id
                else:
                    # 새 상품 추가
                    self.add_product(
                        name=name,
                        category=self._guess_category(name),
                        weight=weight,
                        price=price,
                        stock=stock,
                        product_id=product_id,
                    )
                    # product_idx 설정
                    product = self._products[product_id]
                    product.product_idx = product_idx
                    self._product_idx_to_id[product_idx] = product_id

                loaded_count += 1

            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to load product from IF11: {item}, error: {e}")
                continue

        logger.info(f"Loaded {loaded_count} products from IF11 format")

        # 자동 매칭 시도
        if loaded_count > 0:
            matched = self.auto_match_yolo_to_if11()
            logger.info(f"Auto-matched {matched} YOLO classes to IF11 products")

        return loaded_count

    def _get_or_create_id_for_idx(self, product_idx: str) -> int:
        """
        product_idx 문자열에서 내부 ID 매핑.

        Args:
            product_idx: IF11의 product_idx (예: "P17355176364813008")

        Returns:
            내부 product_id (정수)
        """
        # product_idx → product_id 매핑 캐시 (없으면 생성)
        if not hasattr(self, "_idx_to_id_map"):
            self._idx_to_id_map: Dict[str, int] = {}

        if product_idx in self._idx_to_id_map:
            return self._idx_to_id_map[product_idx]

        # 새 ID 할당
        new_id = self._next_id
        self._next_id += 1
        self._idx_to_id_map[product_idx] = new_id
        return new_id

    def _guess_category(self, name: str) -> str:
        """
        상품 이름에서 카테고리 추측.

        Args:
            name: 상품 이름

        Returns:
            추측된 카테고리
        """
        name_lower = name.lower()

        # 키워드 기반 카테고리 추측
        if any(kw in name_lower for kw in ["물", "워터", "water", "음료", "주스", "콜라", "사이다"]):
            return "beverage"
        if any(kw in name_lower for kw in ["우유", "milk", "요거트", "치즈"]):
            return "dairy"
        if any(kw in name_lower for kw in ["아이스크림", "하겐다즈", "빙과"]):
            return "frozen"
        if any(kw in name_lower for kw in ["과자", "칩", "스낵", "볼", "깡"]):
            return "snack"
        if any(kw in name_lower for kw in ["초콜릿", "캔디", "젤리", "사탕"]):
            return "candy"
        if any(kw in name_lower for kw in ["김밥", "샌드위치", "삼각", "컵밥", "도시락"]):
            return "food"

        return "etc"

    def export_all(self, exclude_hand: bool = True) -> List[dict]:
        """
        모든 상품을 Node.js 동기화용으로 내보내기.

        Args:
            exclude_hand: hand (class_id=0) 제외 여부

        Returns:
            상품 정보 리스트 (Node.js 형식)
        """
        products = []
        for p in self._products.values():
            if exclude_hand and p.product_id == 0:
                continue
            products.append({
                "productId": p.product_id,
                "name": p.name,
                "category": p.category,
                "weight": p.weight,
                "price": p.price,
                "barcode": p.barcode,
                "stock": p.stock,
                "imageCount": p.image_count,
                "yoloClassId": p.yolo_class_id,
                "yoloClassName": p.yolo_class_name,
                "productIdx": p.product_idx,
            })
        return products

    # =========================================================================
    # YOLO-IF11 매핑 기능
    # =========================================================================

    def get_by_yolo_class_id(self, yolo_class_id: int) -> Optional[ProductInfo]:
        """
        YOLO 클래스 ID로 상품 조회.

        Args:
            yolo_class_id: YOLO 모델의 클래스 ID

        Returns:
            ProductInfo 또는 None
        """
        product_id = self._yolo_to_product.get(yolo_class_id)
        if product_id is not None:
            return self._products.get(product_id)
        return None

    def get_by_yolo_class_name(self, yolo_class_name: str) -> Optional[ProductInfo]:
        """
        YOLO 클래스 이름으로 상품 조회.

        Args:
            yolo_class_name: YOLO 모델의 클래스 이름 (예: "BAG_DALGWANG_DONUT_CHOCO_45G")

        Returns:
            ProductInfo 또는 None
        """
        product_id = self._yolo_name_to_id.get(yolo_class_name)
        if product_id is not None:
            return self._products.get(product_id)
        return None

    def get_by_product_idx(self, product_idx: str) -> Optional[ProductInfo]:
        """
        IF11 상품 ID로 상품 조회.

        Args:
            product_idx: IF11 상품 ID (예: "P17689508539755305")

        Returns:
            ProductInfo 또는 None
        """
        product_id = self._product_idx_to_id.get(product_idx)
        if product_id is not None:
            return self._products.get(product_id)
        return None

    def register_yolo_class(
        self,
        yolo_class_id: int,
        yolo_class_name: str,
        create_product: bool = False,
    ) -> Optional[int]:
        """
        YOLO 클래스를 매핑 테이블에 등록.

        기존 상품이 있으면 매핑만 업데이트하고, 없고 create_product=True면 새 상품 생성.

        Args:
            yolo_class_id: YOLO 클래스 ID
            yolo_class_name: YOLO 클래스 이름
            create_product: 상품이 없을 때 새로 생성할지 여부

        Returns:
            매핑된 product_id 또는 None (생성 안 함)
        """
        # 이미 매핑된 상품이 있는지 확인
        if yolo_class_id in self._yolo_to_product:
            product_id = self._yolo_to_product[yolo_class_id]
            product = self._products.get(product_id)
            if product:
                # 기존 상품에 YOLO 정보 업데이트
                product.yolo_class_id = yolo_class_id
                product.yolo_class_name = yolo_class_name
                self._yolo_name_to_id[yolo_class_name] = product_id
                return product_id

        # yolo_class_id와 같은 product_id가 있는지 확인
        if yolo_class_id in self._products:
            product = self._products[yolo_class_id]
            product.yolo_class_id = yolo_class_id
            product.yolo_class_name = yolo_class_name
            self._yolo_to_product[yolo_class_id] = yolo_class_id
            self._yolo_name_to_id[yolo_class_name] = yolo_class_id
            logger.debug(f"Linked YOLO class {yolo_class_id} to existing product {yolo_class_id}")
            return yolo_class_id

        if not create_product:
            # 매핑 테이블에만 등록 (상품은 나중에 연결)
            self._yolo_name_to_id[yolo_class_name] = -1  # 임시 마커
            logger.debug(f"Registered YOLO class without product: id={yolo_class_id}, name={yolo_class_name}")
            return None

        # 새 상품 생성
        category = self._guess_category(yolo_class_name)
        try:
            product_id = self.add_product(
                name=yolo_class_name,
                category=category,
                weight=0.0,  # IF11 동기화로 업데이트
                price=1000,  # 기본 가격 (IF11 동기화로 업데이트)
                stock=0,
                product_id=yolo_class_id,  # YOLO class_id를 product_id로 사용
            )
            product = self._products[product_id]
            product.yolo_class_id = yolo_class_id
            product.yolo_class_name = yolo_class_name
            self._yolo_to_product[yolo_class_id] = product_id
            self._yolo_name_to_id[yolo_class_name] = product_id
            logger.debug(f"Created product for YOLO class: id={yolo_class_id}, name={yolo_class_name}")
            return product_id
        except ValueError as e:
            logger.warning(f"Failed to create product for YOLO class {yolo_class_id}: {e}")
            return None

    def link_yolo_to_if11(
        self,
        yolo_class_id: int,
        product_idx: str,
        confidence: float = 1.0,
    ) -> bool:
        """
        YOLO 클래스와 IF11 상품을 연결.

        Args:
            yolo_class_id: YOLO 클래스 ID
            product_idx: IF11 상품 ID
            confidence: 매핑 신뢰도 (0.0 ~ 1.0)

        Returns:
            연결 성공 여부
        """
        # IF11 상품 찾기
        if11_product = self.get_by_product_idx(product_idx)
        if if11_product is None:
            logger.warning(f"IF11 product not found: {product_idx}")
            return False

        # YOLO 상품 찾기 또는 IF11 상품에 연결
        yolo_product = self.get_by_yolo_class_id(yolo_class_id)

        if yolo_product is not None and yolo_product.product_id != if11_product.product_id:
            # 둘 다 별도 상품으로 존재 → IF11 상품에 YOLO 정보 병합
            if11_product.yolo_class_id = yolo_class_id
            if11_product.yolo_class_name = yolo_product.yolo_class_name
            # YOLO 상품 제거 (IF11 상품으로 통합)
            self.delete_product(yolo_product.product_id)
            self._yolo_to_product[yolo_class_id] = if11_product.product_id
            if if11_product.yolo_class_name:
                self._yolo_name_to_id[if11_product.yolo_class_name] = if11_product.product_id
            logger.info(
                f"Merged YOLO class {yolo_class_id} into IF11 product {product_idx} "
                f"(product_id={if11_product.product_id})"
            )
        else:
            # IF11 상품에 YOLO 정보 직접 연결
            if11_product.yolo_class_id = yolo_class_id
            self._yolo_to_product[yolo_class_id] = if11_product.product_id
            if if11_product.yolo_class_name:
                self._yolo_name_to_id[if11_product.yolo_class_name] = if11_product.product_id
            logger.info(f"Linked YOLO class {yolo_class_id} to IF11 product {product_idx}")

        return True

    def auto_match_yolo_to_if11(self) -> int:
        """
        YOLO 클래스명과 IF11 상품명을 자동 매칭.

        매칭 전략:
        1. 정규화: 대소문자, 공백, 특수문자 제거
        2. 키워드 추출: 숫자(용량), 브랜드명 분리
        3. 유사도 계산: 공통 키워드 비율
        4. 무게 일치 확인

        Returns:
            매칭된 상품 수
        """
        matched_count = 0

        # YOLO 클래스 정보 수집 (매핑 안 된 것들)
        unlinked_yolo_classes: List[Tuple[int, str]] = []
        for product in self._products.values():
            if product.yolo_class_id is not None and product.product_idx is None:
                # YOLO만 있고 IF11 연결 안 됨
                unlinked_yolo_classes.append((product.yolo_class_id, product.yolo_class_name or product.name))

        # IF11 상품 목록 (YOLO 연결 안 된 것들)
        if11_products: List[ProductInfo] = []
        for product in self._products.values():
            if product.product_idx is not None and product.yolo_class_id is None:
                if11_products.append(product)

        logger.info(
            f"Auto-matching: {len(unlinked_yolo_classes)} YOLO classes, "
            f"{len(if11_products)} IF11 products"
        )

        for yolo_class_id, yolo_class_name in unlinked_yolo_classes:
            best_match: Optional[ProductInfo] = None
            best_score = 0.0

            yolo_keywords = self._extract_keywords(yolo_class_name)
            yolo_weight = self._extract_weight_from_name(yolo_class_name)

            for if11_product in if11_products:
                if11_keywords = self._extract_keywords(if11_product.name)
                score = self._calculate_keyword_similarity(yolo_keywords, if11_keywords)

                # 무게 일치 보너스
                if yolo_weight is not None and if11_product.weight > 0:
                    weight_diff = abs(yolo_weight - if11_product.weight)
                    if weight_diff <= 5:  # 5g 이내
                        score += 0.3
                    elif weight_diff <= 10:  # 10g 이내
                        score += 0.1

                if score > best_score and score >= 0.5:  # 최소 50% 일치
                    best_score = score
                    best_match = if11_product

            if best_match is not None:
                # 매칭 수행
                yolo_product = self.get_by_yolo_class_id(yolo_class_id)
                if yolo_product:
                    # YOLO 상품 정보를 IF11 상품으로 병합
                    best_match.yolo_class_id = yolo_class_id
                    best_match.yolo_class_name = yolo_class_name
                    self._yolo_to_product[yolo_class_id] = best_match.product_id
                    self._yolo_name_to_id[yolo_class_name] = best_match.product_id
                    if yolo_product.product_id != best_match.product_id:
                        self.delete_product(yolo_product.product_id)
                    if11_products.remove(best_match)  # 이미 매칭된 상품 제거
                    matched_count += 1
                    logger.info(
                        f"Auto-matched: YOLO '{yolo_class_name}' -> IF11 '{best_match.name}' "
                        f"(score={best_score:.2f})"
                    )

        logger.info(f"Auto-matching completed: {matched_count} products matched")
        return matched_count

    def _extract_keywords(self, name: str) -> List[str]:
        """
        상품 이름에서 키워드 추출.

        Args:
            name: 상품 이름 (한글/영문)

        Returns:
            키워드 리스트 (소문자, 정규화됨)
        """
        # 특수문자, 밑줄 -> 공백으로 변환
        normalized = re.sub(r'[_\-\.\/\\]', ' ', name)
        # 소문자 변환
        normalized = normalized.lower()
        # 공백으로 분리
        tokens = normalized.split()
        # 짧은 토큰 제거 (1글자 이하)
        keywords = [t for t in tokens if len(t) > 1]
        return keywords

    def _extract_weight_from_name(self, name: str) -> Optional[float]:
        """
        상품 이름에서 무게(g) 또는 용량(ml) 추출.

        Args:
            name: 상품 이름

        Returns:
            무게/용량 (g/ml) 또는 None
        """
        # 패턴: 숫자 + (g|G|ml|ML)
        patterns = [
            r'(\d+)\s*[gG](?:\b|$)',      # 45g, 45G
            r'(\d+)\s*[mM][lL](?:\b|$)',  # 330ml, 500ML
            r'_(\d+)[gG](?:\b|$|_)',      # _45G_
            r'_(\d+)[mM][lL](?:\b|$|_)',  # _330ML_
        ]
        for pattern in patterns:
            match = re.search(pattern, name)
            if match:
                return float(match.group(1))
        return None

    def _calculate_keyword_similarity(
        self,
        keywords1: List[str],
        keywords2: List[str],
    ) -> float:
        """
        두 키워드 리스트의 유사도 계산.

        Args:
            keywords1: 첫 번째 키워드 리스트
            keywords2: 두 번째 키워드 리스트

        Returns:
            유사도 (0.0 ~ 1.0)
        """
        if not keywords1 or not keywords2:
            return 0.0

        set1 = set(keywords1)
        set2 = set(keywords2)

        # 부분 일치도 고려
        common = 0
        for k1 in set1:
            for k2 in set2:
                if k1 == k2:
                    common += 1
                    break
                elif k1 in k2 or k2 in k1:
                    common += 0.5
                    break

        total = max(len(set1), len(set2))
        return common / total if total > 0 else 0.0

    def load_mapping_file(self, path: str) -> int:
        """
        YOLO-IF11 매핑 파일 로드.

        매핑 파일에서 yolo_class_id, yolo_class_name, product_idx를 읽어
        상품 정보를 업데이트합니다.

        Args:
            path: 매핑 파일 경로 (JSON)

        Returns:
            로드된 매핑 수
        """
        if not os.path.exists(path):
            logger.warning(f"Mapping file not found: {path}")
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._mapping_file = path
            loaded_count = 0

            for mapping in data.get("mappings", []):
                yolo_class_id = mapping.get("yolo_class_id")
                yolo_class_name = mapping.get("yolo_class_name")
                product_idx = mapping.get("product_idx")  # IF11 product_idx (null 가능)
                product_name = mapping.get("product_name")
                category = mapping.get("category", "etc")
                weight = mapping.get("weight", 0)
                price = mapping.get("price", 0)

                if yolo_class_id is None:
                    continue

                # YOLO 클래스 등록 (create_product=True로 상품 생성)
                if yolo_class_name:
                    product_id = self.register_yolo_class(
                        yolo_class_id, yolo_class_name, create_product=True
                    )

                    # 상품 정보 업데이트
                    if product_id is not None and product_id in self._products:
                        product = self._products[product_id]

                        # 매핑 파일의 정보로 업데이트
                        if product_name:
                            product.name = product_name
                        if category:
                            product.category = category
                        if weight > 0:
                            product.weight = float(weight)
                        if price > 0:
                            product.price = int(price)

                        # IF11 product_idx 설정 (null이면 None)
                        product.product_idx = product_idx
                        if product_idx:
                            self._product_idx_to_id[product_idx] = product_id

                        loaded_count += 1
                        logger.debug(
                            f"Loaded mapping: yolo_class_id={yolo_class_id}, "
                            f"product_idx={product_idx}, name={product_name}"
                        )

            logger.info(f"Loaded {loaded_count} mappings from {path}")
            return loaded_count

        except Exception as e:
            logger.error(f"Failed to load mapping file {path}: {e}")
            return 0

    def save_mapping_file(self, path: Optional[str] = None) -> bool:
        """
        YOLO-IF11 매핑 파일 저장.

        Args:
            path: 저장 경로 (None이면 로드 시 사용한 경로)

        Returns:
            저장 성공 여부
        """
        save_path = path or self._mapping_file
        if not save_path:
            logger.error("No mapping file path specified")
            return False

        try:
            mappings = []
            for product in self._products.values():
                if product.yolo_class_id is not None or product.product_idx is not None:
                    mapping = {
                        "yolo_class_id": product.yolo_class_id,
                        "yolo_class_name": product.yolo_class_name,
                        "product_idx": product.product_idx,
                        "product_name": product.name,
                        "match_method": "auto" if product.yolo_class_id and product.product_idx else "partial",
                        "confidence": 1.0 if product.yolo_class_id and product.product_idx else 0.5,
                    }
                    mappings.append(mapping)

            data = {
                "version": "1.0",
                "auto_matched": True,
                "mappings": mappings,
            }

            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved {len(mappings)} mappings to {save_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save mapping file {save_path}: {e}")
            return False

    def get_all_yolo_mappings(self) -> List[dict]:
        """
        모든 YOLO-IF11 매핑 정보 조회.

        Returns:
            매핑 정보 리스트
        """
        mappings = []
        for product in self._products.values():
            if product.yolo_class_id is not None:
                mappings.append({
                    "yolo_class_id": product.yolo_class_id,
                    "yolo_class_name": product.yolo_class_name,
                    "product_id": product.product_id,
                    "product_idx": product.product_idx,
                    "product_name": product.name,
                    "weight": product.weight,
                    "price": product.price,
                    "is_linked": product.product_idx is not None,
                })
        return mappings

    def get_yolo_mapping(self, yolo_class_id: int) -> Optional[dict]:
        """
        특정 YOLO 클래스의 매핑 정보 조회.

        Args:
            yolo_class_id: YOLO 클래스 ID

        Returns:
            매핑 정보 또는 None
        """
        product = self.get_by_yolo_class_id(yolo_class_id)
        if product is None:
            return None

        return {
            "yolo_class_id": product.yolo_class_id,
            "yolo_class_name": product.yolo_class_name,
            "product_id": product.product_id,
            "product_idx": product.product_idx,
            "product_name": product.name,
            "weight": product.weight,
            "price": product.price,
            "is_linked": product.product_idx is not None,
        }
