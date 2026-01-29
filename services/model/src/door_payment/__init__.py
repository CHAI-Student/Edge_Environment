"""
Door Payment Controller Module

도어 제어와 결제 흐름을 관리하는 모듈입니다.

흐름:
1. 카드 정보 수신 → 데드볼트 해제 (문 열림 허용)
2. 사용자가 문을 닫음 → 일정 시간 후 데드볼트 잠금
3. 데드볼트 잠금 확인 → 결제 처리

사용 예시:
    from door_payment import DoorPaymentController

    controller = DoorPaymentController(
        io_board_url="http://localhost:8000",
        card_terminal_host="127.0.0.1",
        card_terminal_port=5000
    )

    # 결제 흐름 시작
    result = await controller.process_transaction(
        card_info={"card_number": "..."},
        products=[{"name": "삼각김밥", "price": 1500, "quantity": 1}],
        total_amount=1500
    )
"""

from .controller import DoorPaymentController
from .models import (
    DoorState,
    DeadboltState,
    TransactionState,
    TransactionResult,
    CardInfo,
    ProductItem,
)

__all__ = [
    "DoorPaymentController",
    "DoorState",
    "DeadboltState",
    "TransactionState",
    "TransactionResult",
    "CardInfo",
    "ProductItem",
]
