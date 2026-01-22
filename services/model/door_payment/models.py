"""
Door Payment Controller Data Models

도어 제어 및 결제 흐름에 사용되는 데이터 모델입니다.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class DoorState(str, Enum):
    """도어 상태"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class DeadboltState(str, Enum):
    """데드볼트 상태"""
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"
    UNKNOWN = "UNKNOWN"


class TransactionState(str, Enum):
    """거래 상태"""
    IDLE = "IDLE"                           # 대기 중
    CARD_RECEIVED = "CARD_RECEIVED"         # 카드 정보 수신
    DOOR_UNLOCKED = "DOOR_UNLOCKED"         # 데드볼트 해제 (문 열림 가능)
    DOOR_OPENED = "DOOR_OPENED"             # 문 열림 (사용자 접근 중)
    DOOR_CLOSED = "DOOR_CLOSED"             # 문 닫힘 (잠금 대기)
    DOOR_LOCKED = "DOOR_LOCKED"             # 데드볼트 잠금 완료
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"  # 결제 처리 중
    PAYMENT_COMPLETE = "PAYMENT_COMPLETE"   # 결제 완료
    PAYMENT_FAILED = "PAYMENT_FAILED"       # 결제 실패
    ERROR = "ERROR"                         # 에러 상태


@dataclass
class CardInfo:
    """카드 정보 (간소화된 버전)"""
    card_number: str                        # 마스킹된 카드 번호 (예: ****-****-****-1234)
    card_type: str = "CREDIT"               # CREDIT, DEBIT, PREPAID
    issuer: str = ""                        # 발급사
    received_at: datetime = field(default_factory=datetime.now)


@dataclass
class ProductItem:
    """상품 정보"""
    product_id: str
    name: str
    price: int
    quantity: int = 1

    @property
    def subtotal(self) -> int:
        return self.price * self.quantity


@dataclass
class TransactionResult:
    """거래 결과"""
    success: bool
    transaction_id: str
    state: TransactionState
    products: list[ProductItem]
    total_amount: int
    paid_amount: int = 0
    error_message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        """거래 소요 시간 (초)"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "success": self.success,
            "transaction_id": self.transaction_id,
            "state": self.state.value,
            "products": [
                {
                    "product_id": p.product_id,
                    "name": p.name,
                    "price": p.price,
                    "quantity": p.quantity,
                    "subtotal": p.subtotal,
                }
                for p in self.products
            ],
            "total_amount": self.total_amount,
            "paid_amount": self.paid_amount,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
        }
