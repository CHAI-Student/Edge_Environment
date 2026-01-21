"""
Camera Driver HTTP Client.

camera_driver 서비스와 HTTP 통신을 수행합니다.

Endpoints:
- GET /frame/{camera_id}: 단일 프레임 캡처
- POST /zone/{zone_id}/activate: Zone 카메라 활성화
- POST /zone/{zone_id}/deactivate: Zone 카메라 비활성화
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
import io

import httpx
import numpy as np

from ..config import config

logger = logging.getLogger(__name__)


@dataclass
class CameraStatus:
    """카메라 상태."""

    camera_id: int
    active: bool
    fps: float = 0.0
    resolution: tuple = (640, 480)
    error: Optional[str] = None


class CameraClient:
    """
    Camera Driver HTTP 클라이언트.

    camera_driver 서비스에 HTTP 요청을 보냅니다.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
    ):
        """
        초기화.

        Args:
            base_url: camera_driver 서비스 URL
            timeout: 요청 타임아웃 (초)
        """
        self.base_url = base_url or config.camera_driver_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료."""
        await self.disconnect()

    async def connect(self) -> None:
        """HTTP 클라이언트 연결."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
            logger.info(f"CameraClient connected: {self.base_url}")

    async def disconnect(self) -> None:
        """HTTP 클라이언트 연결 해제."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("CameraClient disconnected")

    async def get_frame(self, camera_id: int) -> Optional[np.ndarray]:
        """
        단일 프레임 캡처.

        Args:
            camera_id: 카메라 ID

        Returns:
            numpy 배열 (BGR 이미지) 또는 None
        """
        if not self._client:
            await self.connect()

        try:
            response = await self._client.get(
                f"/frame/{camera_id}",
                headers={"Accept": "image/jpeg"},
            )
            response.raise_for_status()

            # JPEG 바이트를 numpy 배열로 변환
            import cv2
            img_array = np.frombuffer(response.content, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is None:
                logger.error(f"Failed to decode frame from camera {camera_id}")
                return None

            logger.debug(f"Frame captured: camera={camera_id}, shape={frame.shape}")
            return frame

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting frame: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting frame: {e}")
            return None

    async def get_frame_base64(self, camera_id: int) -> Optional[str]:
        """
        Base64 인코딩된 프레임 캡처.

        Args:
            camera_id: 카메라 ID

        Returns:
            Base64 문자열 또는 None
        """
        if not self._client:
            await self.connect()

        try:
            response = await self._client.get(
                f"/frame/{camera_id}/base64",
            )
            response.raise_for_status()
            data = response.json()
            return data.get("frame")

        except Exception as e:
            logger.error(f"Error getting base64 frame: {e}")
            return None

    async def activate_zone(self, zone_id: int) -> bool:
        """
        Zone 카메라 활성화.

        Args:
            zone_id: Zone ID (0-4)

        Returns:
            성공 여부
        """
        if not self._client:
            await self.connect()

        try:
            response = await self._client.post(f"/zone/{zone_id}/activate")
            response.raise_for_status()
            logger.info(f"Zone {zone_id} camera activated")
            return True

        except Exception as e:
            logger.error(f"Error activating zone {zone_id}: {e}")
            return False

    async def deactivate_zone(self, zone_id: int) -> bool:
        """
        Zone 카메라 비활성화.

        Args:
            zone_id: Zone ID (0-4)

        Returns:
            성공 여부
        """
        if not self._client:
            await self.connect()

        try:
            response = await self._client.post(f"/zone/{zone_id}/deactivate")
            response.raise_for_status()
            logger.info(f"Zone {zone_id} camera deactivated")
            return True

        except Exception as e:
            logger.error(f"Error deactivating zone {zone_id}: {e}")
            return False

    async def get_status(self) -> dict:
        """
        전체 카메라 상태 조회.

        Returns:
            카메라 상태 딕셔너리
        """
        if not self._client:
            await self.connect()

        try:
            response = await self._client.get("/status")
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error getting camera status: {e}")
            return {}

    async def health_check(self) -> bool:
        """
        헬스 체크.

        Returns:
            서비스 정상 여부
        """
        if not self._client:
            await self.connect()

        try:
            response = await self._client.get("/health")
            return response.status_code == 200

        except Exception as e:
            logger.error(f"Camera driver health check failed: {e}")
            return False

    async def save_snapshot(
        self,
        camera_id: int,
        folder_path: str,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        스냅샷을 파일로 저장.

        Args:
            camera_id: 카메라 ID
            folder_path: 저장 폴더 경로
            filename: 파일명 (None이면 자동 생성)

        Returns:
            저장된 파일 경로 또는 None
        """
        frame = await self.get_frame(camera_id)
        if frame is None:
            return None

        import os
        import time
        import cv2

        os.makedirs(folder_path, exist_ok=True)

        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"cam{camera_id}_{timestamp}.jpg"

        filepath = os.path.join(folder_path, filename)
        cv2.imwrite(filepath, frame)
        logger.info(f"Snapshot saved: {filepath}")

        return filepath
