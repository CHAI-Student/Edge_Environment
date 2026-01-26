"""
Node.js HTTP Client.

Model 서비스에서 Node.js Orchestrator로 결과 전송.

사용 예시:
    client = NodeJSClient("http://localhost:8889")
    await client.send_judgment(zone_id=0, result=judgment_result)
"""

from typing import Optional
import logging
import httpx

from ..engine.models import JudgmentResult

logger = logging.getLogger(__name__)


class NodeJSClient:
    """
    Node.js Orchestrator HTTP 클라이언트.

    Model 서비스에서 판단 결과를 Node.js로 전송합니다.

    Attributes:
        base_url: Node.js 서버 URL
        timeout: HTTP 요청 타임아웃 (초)
        _client: httpx 비동기 클라이언트
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8889",
        timeout: float = 10.0,
    ):
        """
        클라이언트 초기화.

        Args:
            base_url: Node.js 서버 URL
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        logger.info(f"NodeJSClient initialized: {self.base_url}")

    async def start(self) -> None:
        """클라이언트 시작."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
            logger.info("NodeJSClient started")

    async def stop(self) -> None:
        """클라이언트 종료."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("NodeJSClient stopped")

    async def send_judgment(
        self,
        zone_id: int,
        result: JudgmentResult,
    ) -> bool:
        """
        판단 결과를 Node.js로 전송.

        Args:
            zone_id: Zone ID
            result: JudgmentResult 인스턴스

        Returns:
            전송 성공 여부
        """
        if self._client is None:
            await self.start()

        endpoint = "/api/sensor/judgment"

        payload = {
            "zoneId": zone_id,
            **result.to_node_response(),
        }

        try:
            response = await self._client.post(endpoint, json=payload)

            if response.status_code == 200:
                logger.info(
                    f"Judgment sent to Node.js: zone={zone_id}, "
                    f"status={result.status.value}, products={len(result.products)}"
                )
                return True
            else:
                logger.warning(
                    f"Node.js returned {response.status_code}: {response.text}"
                )
                return False

        except httpx.TimeoutException:
            logger.error(f"Timeout sending judgment to Node.js: {endpoint}")
            return False

        except httpx.HTTPError as e:
            logger.error(f"HTTP error sending judgment: {e}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error sending judgment: {e}", exc_info=True)
            return False

    async def send_weight_event(
        self,
        zone_id: int,
        delta_weight: float,
        channels: list,
    ) -> bool:
        """
        무게 변화 이벤트를 Node.js로 전송.

        Args:
            zone_id: Zone ID
            delta_weight: 무게 변화량 (g)
            channels: 변화 감지된 채널 인덱스 리스트

        Returns:
            전송 성공 여부
        """
        if self._client is None:
            await self.start()

        endpoint = "/api/sensor/weight-change"

        payload = {
            "zoneId": zone_id,
            "deltaWeight": delta_weight,
            "channels": channels,
            "eventType": "weight_change",
        }

        try:
            response = await self._client.post(endpoint, json=payload)

            if response.status_code == 200:
                logger.debug(f"Weight event sent: zone={zone_id}, delta={delta_weight:.1f}g")
                return True
            else:
                logger.warning(
                    f"Node.js returned {response.status_code} for weight event"
                )
                return False

        except Exception as e:
            logger.error(f"Error sending weight event: {e}")
            return False

    async def send_camera_event(
        self,
        zone_id: int,
        camera_id: int,
        event_type: str,  # "activated" or "deactivated"
    ) -> bool:
        """
        카메라 상태 이벤트를 Node.js로 전송.

        Args:
            zone_id: Zone ID
            camera_id: 카메라 ID
            event_type: 이벤트 타입 ("activated" 또는 "deactivated")

        Returns:
            전송 성공 여부
        """
        if self._client is None:
            await self.start()

        endpoint = "/api/sensor/camera-event"

        payload = {
            "zoneId": zone_id,
            "cameraId": camera_id,
            "eventType": event_type,
        }

        try:
            response = await self._client.post(endpoint, json=payload)

            if response.status_code == 200:
                logger.debug(f"Camera event sent: zone={zone_id}, camera={camera_id}, type={event_type}")
                return True
            else:
                logger.warning(
                    f"Node.js returned {response.status_code} for camera event"
                )
                return False

        except Exception as e:
            logger.error(f"Error sending camera event: {e}")
            return False

    async def health_check(self) -> bool:
        """
        Node.js 서버 헬스 체크.

        Returns:
            서버 정상 여부
        """
        if self._client is None:
            await self.start()

        try:
            response = await self._client.get("/api/health")
            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Node.js health check failed: {e}")
            return False

    async def __aenter__(self) -> "NodeJSClient":
        """Context manager 진입."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager 종료."""
        await self.stop()

    # =========================================================================
    # Product Sync (상품 동기화)
    # =========================================================================

    async def sync_products_to_server(self, products: list) -> bool:
        """
        상품 목록을 서버 DB로 전송.

        Node.js Orchestrator가 서버 DB로 전달합니다.

        Args:
            products: 상품 정보 리스트 (export_all 형식)

        Returns:
            전송 성공 여부
        """
        if self._client is None:
            await self.start()

        endpoint = "/api/products/bulk"

        payload = {
            "products": products,
            "count": len(products),
            "syncType": "full",  # full 또는 incremental
        }

        try:
            response = await self._client.post(endpoint, json=payload)

            if response.status_code == 200:
                logger.info(f"Products synced to server: {len(products)} products")
                return True
            else:
                logger.warning(
                    f"Server returned {response.status_code} for product sync"
                )
                return False

        except httpx.TimeoutException:
            logger.error("Timeout syncing products to server")
            return False

        except httpx.HTTPError as e:
            logger.error(f"HTTP error syncing products: {e}")
            return False

        except Exception as e:
            logger.error(f"Error syncing products: {e}", exc_info=True)
            return False

    async def sync_single_product(
        self,
        product: dict,
        action: str = "upsert",  # upsert, delete
    ) -> bool:
        """
        단일 상품 동기화.

        Args:
            product: 상품 정보
            action: 동작 (upsert=등록/수정, delete=삭제)

        Returns:
            전송 성공 여부
        """
        if self._client is None:
            await self.start()

        endpoint = "/api/products/sync"

        payload = {
            "product": product,
            "action": action,
        }

        try:
            response = await self._client.post(endpoint, json=payload)

            if response.status_code == 200:
                logger.info(f"Product synced: {action} - {product.get('name')}")
                return True
            else:
                logger.warning(
                    f"Server returned {response.status_code} for product sync"
                )
                return False

        except Exception as e:
            logger.error(f"Error syncing product: {e}")
            return False

    async def notify_product_registered(
        self,
        product_id: int,
        name: str,
        price: int,
    ) -> bool:
        """
        상품 등록 알림.

        Args:
            product_id: 상품 ID
            name: 상품 이름
            price: 가격

        Returns:
            전송 성공 여부
        """
        if self._client is None:
            await self.start()

        endpoint = "/api/events/product-registered"

        payload = {
            "eventType": "product_registered",
            "productId": product_id,
            "name": name,
            "price": price,
        }

        try:
            response = await self._client.post(endpoint, json=payload)
            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Product registration notification failed: {e}")
            return False
