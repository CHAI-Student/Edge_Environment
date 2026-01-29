"""
Payment Client for card_terminal REST API integration.

card_terminal 서비스의 REST API를 호출하여 결제를 처리합니다.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)


class PaymentStatus(str, Enum):
    """결제 상태"""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


@dataclass
class PaymentResult:
    """결제 결과"""
    success: bool
    status: PaymentStatus
    response_code: int
    response_code_name: str
    message: str
    authorization_number: Optional[str] = None
    vankey: Optional[str] = None
    card_info: Optional[dict] = None


class PaymentClient:
    """
    card_terminal REST API 클라이언트

    card_terminal 서비스(포트 8004)와 통신하여 결제를 처리합니다.

    사용법:
        client = PaymentClient(base_url="http://127.0.0.1:8004")

        # 디바이스 상태 확인
        status = await client.check_device()

        # 토큰 결제 승인
        result = await client.approve_token_payment(amount="1500")

        # 토큰 결제 취소
        result = await client.cancel_token_payment(
            amount="1500",
            authorization_number="12345678",
            authorization_date="260122"
        )
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8004",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Args:
            base_url: card_terminal REST API 기본 URL
            api_key: API 인증 키 (선택)
            timeout: 요청 타임아웃 (초)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    def _get_headers(self) -> dict:
        """요청 헤더 생성"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def check_device(self) -> dict:
        """
        디바이스 상태 확인

        Returns:
            dict: 디바이스 상태 정보
                - status: 연결 상태 ("connected", "not_initialized", "error")
                - response_code: 응답 코드 (연결된 경우)
                - message: 상태 메시지
        """
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.base_url}/status",
                    headers=self._get_headers()
                ) as response:
                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Device check failed: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error during device check: {e}")
            return {"status": "error", "message": "Connection failed"}

    async def health_check(self) -> bool:
        """
        서비스 헬스 체크

        Returns:
            bool: 서비스가 정상인지 여부
        """
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("status") == "healthy"
                    return False
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def approve_token_payment(self, amount: str) -> PaymentResult:
        """
        토큰 결제 승인

        토큰을 생성하고 해당 토큰으로 결제를 승인합니다.

        Args:
            amount: 결제 금액 (숫자 문자열)

        Returns:
            PaymentResult: 결제 결과
        """
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/payment/token/approve",
                    headers=self._get_headers(),
                    json={"amount": amount}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return PaymentResult(
                            success=data.get("success", False),
                            status=(
                                PaymentStatus.SUCCESS
                                if data.get("success")
                                else PaymentStatus.FAILED
                            ),
                            response_code=data.get("response_code", -1),
                            response_code_name=data.get("response_code_name", "UNKNOWN"),
                            message=data.get("message", ""),
                            authorization_number=data.get("authorization_number"),
                            vankey=data.get("vankey"),
                            card_info=data.get("card_info"),
                        )
                    elif response.status == 401:
                        return PaymentResult(
                            success=False,
                            status=PaymentStatus.ERROR,
                            response_code=-1,
                            response_code_name="AUTH_ERROR",
                            message="API authentication failed",
                        )
                    elif response.status == 503:
                        return PaymentResult(
                            success=False,
                            status=PaymentStatus.ERROR,
                            response_code=-1,
                            response_code_name="SERVICE_UNAVAILABLE",
                            message="Card terminal not initialized",
                        )
                    else:
                        error_data = await response.json()
                        return PaymentResult(
                            success=False,
                            status=PaymentStatus.ERROR,
                            response_code=-1,
                            response_code_name="HTTP_ERROR",
                            message=error_data.get("detail", f"HTTP {response.status}"),
                        )
        except aiohttp.ClientError as e:
            logger.error(f"Token payment approval failed: {e}")
            return PaymentResult(
                success=False,
                status=PaymentStatus.ERROR,
                response_code=-1,
                response_code_name="CONNECTION_ERROR",
                message=str(e),
            )
        except Exception as e:
            logger.error(f"Unexpected error during token payment: {e}")
            return PaymentResult(
                success=False,
                status=PaymentStatus.ERROR,
                response_code=-1,
                response_code_name="UNKNOWN_ERROR",
                message="Payment processing failed",
            )

    async def cancel_token_payment(
        self,
        amount: str,
        authorization_number: str,
        authorization_date: str,
    ) -> PaymentResult:
        """
        토큰 결제 취소

        Args:
            amount: 취소 금액 (숫자 문자열)
            authorization_number: 원래 승인 번호 (8자리)
            authorization_date: 원래 승인 일자 (YYMMDD 형식)

        Returns:
            PaymentResult: 취소 결과
        """
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/payment/token/cancel",
                    headers=self._get_headers(),
                    json={
                        "amount": amount,
                        "original_authorization_number": authorization_number,
                        "original_authorization_date": authorization_date,
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return PaymentResult(
                            success=data.get("success", False),
                            status=(
                                PaymentStatus.CANCELLED
                                if data.get("success")
                                else PaymentStatus.FAILED
                            ),
                            response_code=data.get("response_code", -1),
                            response_code_name=data.get("response_code_name", "UNKNOWN"),
                            message=data.get("message", ""),
                            vankey=data.get("vankey"),
                            card_info=data.get("card_info"),
                        )
                    else:
                        error_data = await response.json()
                        return PaymentResult(
                            success=False,
                            status=PaymentStatus.ERROR,
                            response_code=-1,
                            response_code_name="HTTP_ERROR",
                            message=error_data.get("detail", f"HTTP {response.status}"),
                        )
        except aiohttp.ClientError as e:
            logger.error(f"Token payment cancellation failed: {e}")
            return PaymentResult(
                success=False,
                status=PaymentStatus.ERROR,
                response_code=-1,
                response_code_name="CONNECTION_ERROR",
                message=str(e),
            )
        except Exception as e:
            logger.error(f"Unexpected error during token cancel: {e}")
            return PaymentResult(
                success=False,
                status=PaymentStatus.ERROR,
                response_code=-1,
                response_code_name="UNKNOWN_ERROR",
                message="Payment cancellation failed",
            )
