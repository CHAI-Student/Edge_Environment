"""
Door Payment Controller

카드 정보 수신 → 데드볼트 해제 → 문 닫힘 감지 → 데드볼트 잠금 → 결제 처리
흐름을 관리하는 컨트롤러입니다.

Note: 실제 결제 처리(card_terminal 연동)는 추후 다른 개발자가 구현할 예정입니다.
      이 모듈은 기본 흐름과 상태 관리를 제공합니다.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

import aiohttp

from .models import (
    CardInfo,
    DeadboltState,
    DoorState,
    ProductItem,
    TransactionResult,
    TransactionState,
)

logger = logging.getLogger(__name__)


class DoorPaymentController:
    """
    도어 제어 + 결제 흐름 컨트롤러

    흐름:
    1. 카드 정보 수신 → 데드볼트 해제 (문 열림 허용)
    2. 사용자가 문을 닫음 → 일정 시간(lock_delay_seconds) 후 데드볼트 잠금
    3. 데드볼트 잠금 확인 → 결제 처리 (card_terminal 호출)

    사용법:
        controller = DoorPaymentController(io_board_url="http://localhost:8001")

        result = await controller.process_transaction(
            card_info=CardInfo(card_number="****-****-****-1234"),
            products=[ProductItem(product_id="1", name="삼각김밥", price=1500)],
            total_amount=1500
        )
    """

    def __init__(
        self,
        io_board_url: str = "http://localhost:8001",
        card_terminal_host: str = "127.0.0.1",
        card_terminal_port: int = 5000,
        lock_delay_seconds: float = 3.0,
        door_check_interval_seconds: float = 0.5,
        door_timeout_seconds: float = 120.0,
    ):
        """
        Args:
            io_board_url: io_board 서비스 URL
            card_terminal_host: card_terminal 서비스 호스트
            card_terminal_port: card_terminal 서비스 포트
            lock_delay_seconds: 문 닫힘 후 데드볼트 잠금까지 대기 시간 (초)
            door_check_interval_seconds: 도어 상태 체크 간격 (초)
            door_timeout_seconds: 도어 타임아웃 (초) - 이 시간 내에 문이 닫히지 않으면 에러
        """
        self.io_board_url = io_board_url.rstrip("/")
        self.card_terminal_host = card_terminal_host
        self.card_terminal_port = card_terminal_port
        self.lock_delay_seconds = lock_delay_seconds
        self.door_check_interval_seconds = door_check_interval_seconds
        self.door_timeout_seconds = door_timeout_seconds

        # 현재 거래 상태
        self._current_state = TransactionState.IDLE
        self._current_transaction_id: Optional[str] = None

    @property
    def current_state(self) -> TransactionState:
        return self._current_state

    async def process_transaction(
        self,
        card_info: CardInfo,
        products: list[ProductItem],
        total_amount: int,
    ) -> TransactionResult:
        """
        전체 거래 흐름 처리

        Args:
            card_info: 카드 정보
            products: 구매 상품 목록
            total_amount: 총 결제 금액

        Returns:
            TransactionResult: 거래 결과
        """
        transaction_id = str(uuid.uuid4())[:8]
        self._current_transaction_id = transaction_id
        started_at = datetime.now()

        logger.info(f"[{transaction_id}] 거래 시작 - 총액: {total_amount}원")

        try:
            # 1. 카드 정보 수신 확인
            self._current_state = TransactionState.CARD_RECEIVED
            logger.info(f"[{transaction_id}] 카드 정보 수신: {card_info.card_number}")

            # 2. 데드볼트 해제 (문 열림 허용)
            await self._unlock_deadbolt()
            self._current_state = TransactionState.DOOR_UNLOCKED
            logger.info(f"[{transaction_id}] 데드볼트 해제 완료 - 문 열림 가능")

            # 3. 문이 열렸다가 닫히는 것을 감지
            await self._wait_for_door_cycle()
            self._current_state = TransactionState.DOOR_CLOSED
            logger.info(f"[{transaction_id}] 문 닫힘 감지")

            # 4. 일정 시간 후 데드볼트 잠금
            logger.info(f"[{transaction_id}] {self.lock_delay_seconds}초 후 데드볼트 잠금...")
            await asyncio.sleep(self.lock_delay_seconds)

            await self._lock_deadbolt()
            self._current_state = TransactionState.DOOR_LOCKED
            logger.info(f"[{transaction_id}] 데드볼트 잠금 완료")

            # 5. 결제 처리
            self._current_state = TransactionState.PAYMENT_PROCESSING
            logger.info(f"[{transaction_id}] 결제 처리 시작...")

            payment_success = await self._process_payment(
                card_info=card_info,
                total_amount=total_amount,
            )

            if payment_success:
                self._current_state = TransactionState.PAYMENT_COMPLETE
                logger.info(f"[{transaction_id}] 결제 완료 - {total_amount}원")
            else:
                self._current_state = TransactionState.PAYMENT_FAILED
                logger.error(f"[{transaction_id}] 결제 실패")

            completed_at = datetime.now()

            return TransactionResult(
                success=payment_success,
                transaction_id=transaction_id,
                state=self._current_state,
                products=products,
                total_amount=total_amount,
                paid_amount=total_amount if payment_success else 0,
                error_message="" if payment_success else "Payment processing failed",
                started_at=started_at,
                completed_at=completed_at,
            )

        except asyncio.TimeoutError as e:
            self._current_state = TransactionState.ERROR
            logger.error(f"[{transaction_id}] 타임아웃: {e}")
            return TransactionResult(
                success=False,
                transaction_id=transaction_id,
                state=self._current_state,
                products=products,
                total_amount=total_amount,
                error_message=f"Timeout: {str(e)}",
                started_at=started_at,
                completed_at=datetime.now(),
            )
        except Exception as e:
            self._current_state = TransactionState.ERROR
            logger.error(f"[{transaction_id}] 에러: {e}")
            return TransactionResult(
                success=False,
                transaction_id=transaction_id,
                state=self._current_state,
                products=products,
                total_amount=total_amount,
                error_message=str(e),
                started_at=started_at,
                completed_at=datetime.now(),
            )
        finally:
            self._current_state = TransactionState.IDLE
            self._current_transaction_id = None

    async def _get_io_status(self) -> dict:
        """io_board에서 현재 도어/데드볼트 상태 조회"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.io_board_url}/io-status") as response:
                response.raise_for_status()
                return await response.json()

    async def _get_door_state(self) -> DoorState:
        """현재 도어 상태 조회"""
        try:
            status = await self._get_io_status()
            door_str = status.get("door", "").upper()
            if "OPEN" in door_str:
                return DoorState.OPEN
            elif "CLOSE" in door_str:
                return DoorState.CLOSED
            return DoorState.UNKNOWN
        except Exception as e:
            logger.warning(f"도어 상태 조회 실패: {e}")
            return DoorState.UNKNOWN

    async def _get_deadbolt_state(self) -> DeadboltState:
        """현재 데드볼트 상태 조회"""
        try:
            status = await self._get_io_status()
            deadbolt_str = status.get("deadbolt", "").upper()
            if "LOCK" in deadbolt_str or "CLOSE" in deadbolt_str:
                return DeadboltState.LOCKED
            elif "UNLOCK" in deadbolt_str or "OPEN" in deadbolt_str:
                return DeadboltState.UNLOCKED
            return DeadboltState.UNKNOWN
        except Exception as e:
            logger.warning(f"데드볼트 상태 조회 실패: {e}")
            return DeadboltState.UNKNOWN

    async def _unlock_deadbolt(self) -> None:
        """데드볼트 해제 (문 열림 가능 상태로)"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.io_board_url}/deadbolt",
                json={"state": "open"},
            ) as response:
                response.raise_for_status()
                result = await response.json()
                logger.debug(f"데드볼트 해제 응답: {result}")

    async def _lock_deadbolt(self) -> None:
        """데드볼트 잠금"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.io_board_url}/deadbolt",
                json={"state": "close"},
            ) as response:
                response.raise_for_status()
                result = await response.json()
                logger.debug(f"데드볼트 잠금 응답: {result}")

    async def _wait_for_door_cycle(self) -> None:
        """
        문이 열렸다가 닫히는 것을 대기

        1. 문이 열릴 때까지 대기 (사용자가 문을 엶)
        2. 문이 닫힐 때까지 대기 (사용자가 상품 꺼내고 문을 닫음)
        """
        timeout = self.door_timeout_seconds
        elapsed = 0.0

        # 1. 문이 열릴 때까지 대기
        logger.debug("문 열림 대기 중...")
        while elapsed < timeout:
            state = await self._get_door_state()
            if state == DoorState.OPEN:
                self._current_state = TransactionState.DOOR_OPENED
                logger.debug("문 열림 감지")
                break
            await asyncio.sleep(self.door_check_interval_seconds)
            elapsed += self.door_check_interval_seconds
        else:
            raise asyncio.TimeoutError("Door open timeout")

        # 2. 문이 닫힐 때까지 대기
        logger.debug("문 닫힘 대기 중...")
        while elapsed < timeout:
            state = await self._get_door_state()
            if state == DoorState.CLOSED:
                logger.debug("문 닫힘 감지")
                return
            await asyncio.sleep(self.door_check_interval_seconds)
            elapsed += self.door_check_interval_seconds

        raise asyncio.TimeoutError("Door close timeout")

    async def _process_payment(
        self,
        card_info: CardInfo,
        total_amount: int,
    ) -> bool:
        """
        결제 처리

        Note: 이 메서드는 현재 스텁 구현입니다.
              실제 card_terminal 연동은 추후 구현 예정입니다.

        Args:
            card_info: 카드 정보
            total_amount: 결제 금액

        Returns:
            bool: 결제 성공 여부
        """
        # TODO: card_terminal 서비스와 연동하여 실제 결제 처리
        # 현재는 시뮬레이션을 위해 항상 성공 반환
        logger.info(
            f"[결제 처리] 카드: {card_info.card_number}, "
            f"금액: {total_amount}원 - 결제 시뮬레이션"
        )

        # 결제 처리 시뮬레이션 (실제 구현 시 제거)
        await asyncio.sleep(0.5)

        # TODO: 아래 코드로 card_terminal 연동 구현 필요
        # try:
        #     reader, writer = await asyncio.open_connection(
        #         self.card_terminal_host,
        #         self.card_terminal_port
        #     )
        #     # ... 결제 요청 전송 및 응답 수신 ...
        #     writer.close()
        #     await writer.wait_closed()
        #     return True
        # except Exception as e:
        #     logger.error(f"결제 처리 실패: {e}")
        #     return False

        return True  # 시뮬레이션: 항상 성공

    async def cancel_transaction(self) -> bool:
        """
        현재 진행 중인 거래 취소

        Returns:
            bool: 취소 성공 여부
        """
        if self._current_state == TransactionState.IDLE:
            logger.warning("취소할 거래가 없습니다")
            return False

        logger.info(f"[{self._current_transaction_id}] 거래 취소 요청")

        # 데드볼트 잠금 (안전 조치)
        try:
            await self._lock_deadbolt()
        except Exception as e:
            logger.error(f"거래 취소 중 데드볼트 잠금 실패: {e}")

        self._current_state = TransactionState.IDLE
        self._current_transaction_id = None
        return True

    async def emergency_lock(self) -> bool:
        """
        긴급 잠금 (데드볼트 즉시 잠금)

        Returns:
            bool: 잠금 성공 여부
        """
        logger.warning("긴급 잠금 실행")
        try:
            await self._lock_deadbolt()
            return True
        except Exception as e:
            logger.error(f"긴급 잠금 실패: {e}")
            return False
