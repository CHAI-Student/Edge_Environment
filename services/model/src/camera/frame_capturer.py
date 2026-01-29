"""
Frame Capturer.

Top + Side 카메라에서 동시에 프레임을 캡처합니다.

두 가지 모드 지원:
1. API 모드: camera_driver HTTP API를 통해 실시간 캡처
2. 폴더 모드: 미리 합의된 경로에서 저장된 이미지를 직접 로드
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional, List, Tuple
import time

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from .camera_client import CameraClient
from ..config import (
    config,
    get_zone_cameras,
    TOP_CAMERA_ID,
    get_enabled_zones,
    get_top_camera_path,
    get_side_camera_path,
    get_snapshot_folder,
)

logger = logging.getLogger(__name__)


@dataclass
class CapturedFrames:
    """캡처된 프레임 세트."""

    zone_id: int
    top_frame: Optional[np.ndarray]
    side_frame: Optional[np.ndarray]
    top_camera_id: int
    side_camera_id: int
    timestamp: float

    @property
    def has_both(self) -> bool:
        """양쪽 프레임이 모두 있는지."""
        return self.top_frame is not None and self.side_frame is not None

    @property
    def has_any(self) -> bool:
        """적어도 하나의 프레임이 있는지."""
        return self.top_frame is not None or self.side_frame is not None


class FrameCapturer:
    """
    프레임 캡처러.

    Zone에 대해 Top + Side 카메라에서 동시에 프레임을 캡처합니다.

    사용 예시:
        async with FrameCapturer() as capturer:
            frames = await capturer.capture_zone(zone_id=0)
            if frames.has_both:
                process(frames.top_frame, frames.side_frame)
    """

    def __init__(
        self,
        camera_client: Optional[CameraClient] = None,
        auto_activate: bool = True,
        capture_delay: float = 0.1,  # Zone 활성화 후 대기 시간
    ):
        """
        초기화.

        Args:
            camera_client: CameraClient 인스턴스 (None이면 생성)
            auto_activate: Zone 활성화 자동 수행
            capture_delay: Zone 활성화 후 캡처 전 대기 시간 (초)
        """
        self.camera_client = camera_client
        self.auto_activate = auto_activate
        self.capture_delay = capture_delay
        self._owns_client = camera_client is None

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입."""
        if self._owns_client:
            self.camera_client = CameraClient()
            await self.camera_client.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료."""
        if self._owns_client and self.camera_client:
            await self.camera_client.disconnect()

    async def capture_zone(self, zone_id: int) -> CapturedFrames:
        """
        Zone에 대한 Top + Side 프레임 캡처.

        Args:
            zone_id: Zone ID (0-4)

        Returns:
            CapturedFrames
        """
        top_cam_id, side_cam_id = get_zone_cameras(zone_id)
        timestamp = time.time()

        # Zone 활성화 (필요시)
        if self.auto_activate:
            await self.camera_client.activate_zone(zone_id)
            if self.capture_delay > 0:
                await asyncio.sleep(self.capture_delay)

        # 동시 캡처
        try:
            top_frame, side_frame = await asyncio.gather(
                self.camera_client.get_frame(top_cam_id),
                self.camera_client.get_frame(side_cam_id),
            )
        except Exception as e:
            logger.error(f"Error capturing frames for zone {zone_id}: {e}")
            top_frame = None
            side_frame = None

        return CapturedFrames(
            zone_id=zone_id,
            top_frame=top_frame,
            side_frame=side_frame,
            top_camera_id=top_cam_id,
            side_camera_id=side_cam_id,
            timestamp=timestamp,
        )

    async def capture_top_only(self) -> Optional[np.ndarray]:
        """
        Top 카메라만 캡처.

        Returns:
            Top 프레임 또는 None
        """
        return await self.camera_client.get_frame(TOP_CAMERA_ID)

    async def capture_side_only(self, zone_id: int) -> Optional[np.ndarray]:
        """
        특정 Zone의 Side 카메라만 캡처.

        Args:
            zone_id: Zone ID

        Returns:
            Side 프레임 또는 None
        """
        _, side_cam_id = get_zone_cameras(zone_id)
        return await self.camera_client.get_frame(side_cam_id)

    async def capture_multiple_zones(
        self,
        zone_ids: List[int],
    ) -> List[CapturedFrames]:
        """
        여러 Zone 동시 캡처.

        Args:
            zone_ids: Zone ID 리스트

        Returns:
            CapturedFrames 리스트
        """
        tasks = [self.capture_zone(z) for z in zone_ids]
        return await asyncio.gather(*tasks)

    async def deactivate_zone(self, zone_id: int) -> bool:
        """
        Zone 카메라 비활성화.

        Args:
            zone_id: Zone ID

        Returns:
            성공 여부
        """
        return await self.camera_client.deactivate_zone(zone_id)

    async def save_zone_snapshots(
        self,
        zone_id: int,
        folder_path: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Zone의 Top + Side 스냅샷 저장.

        Args:
            zone_id: Zone ID
            folder_path: 저장 폴더

        Returns:
            (top_path, side_path) 튜플
        """
        frames = await self.capture_zone(zone_id)

        import os
        import cv2

        os.makedirs(folder_path, exist_ok=True)

        top_path = None
        side_path = None

        timestamp = time.strftime("%Y%m%d_%H%M%S")

        if frames.top_frame is not None:
            top_path = os.path.join(folder_path, f"top_{timestamp}.jpg")
            cv2.imwrite(top_path, frames.top_frame)

        if frames.side_frame is not None:
            side_path = os.path.join(folder_path, f"side_zone{zone_id}_{timestamp}.jpg")
            cv2.imwrite(side_path, frames.side_frame)

        return top_path, side_path


class FolderFrameLoader:
    """
    폴더 기반 프레임 로더.

    미리 합의된 경로에서 저장된 이미지를 직접 로드합니다.
    camera_driver HTTP API 대신 파일 시스템에서 직접 읽음.

    사용 예시:
        loader = FolderFrameLoader()
        frames = loader.load_zone(session_id="260121_143025", zone_id=0)
        if frames.has_both:
            process(frames.top_frame, frames.side_frame)
    """

    def __init__(self):
        """초기화."""
        if not HAS_CV2:
            logger.warning("OpenCV not available, image loading will fail")

    def load_zone(self, session_id: str, zone_id: int) -> CapturedFrames:
        """
        Zone에 대한 Top + Side 이미지 로드.

        Args:
            session_id: 세션 ID (예: "260121_143025")
            zone_id: Zone ID (0-4)

        Returns:
            CapturedFrames
        """
        top_cam_id, side_cam_id = get_zone_cameras(zone_id)
        timestamp = time.time()

        top_frame = None
        side_frame = None

        # Top 이미지 로드
        top_path = get_top_camera_path(session_id)
        if os.path.exists(top_path):
            try:
                top_frame = cv2.imread(top_path)
                if top_frame is not None:
                    logger.debug(f"Loaded top image: {top_path}")
                else:
                    logger.warning(f"Failed to decode top image: {top_path}")
            except Exception as e:
                logger.error(f"Error loading top image {top_path}: {e}")
        else:
            logger.warning(f"Top image not found: {top_path}")

        # Side 이미지 로드
        side_path = get_side_camera_path(session_id, zone_id)
        if os.path.exists(side_path):
            try:
                side_frame = cv2.imread(side_path)
                if side_frame is not None:
                    logger.debug(f"Loaded side image: {side_path}")
                else:
                    logger.warning(f"Failed to decode side image: {side_path}")
            except Exception as e:
                logger.error(f"Error loading side image {side_path}: {e}")
        else:
            logger.warning(f"Side image not found: {side_path}")

        return CapturedFrames(
            zone_id=zone_id,
            top_frame=top_frame,
            side_frame=side_frame,
            top_camera_id=top_cam_id,
            side_camera_id=side_cam_id,
            timestamp=timestamp,
        )

    def load_top_only(self, session_id: str) -> Optional[np.ndarray]:
        """
        Top 이미지만 로드.

        Args:
            session_id: 세션 ID

        Returns:
            Top 프레임 또는 None
        """
        top_path = get_top_camera_path(session_id)
        if os.path.exists(top_path):
            try:
                return cv2.imread(top_path)
            except Exception as e:
                logger.error(f"Error loading top image: {e}")
        return None

    def load_side_only(self, session_id: str, zone_id: int) -> Optional[np.ndarray]:
        """
        특정 Zone의 Side 이미지만 로드.

        Args:
            session_id: 세션 ID
            zone_id: Zone ID

        Returns:
            Side 프레임 또는 None
        """
        side_path = get_side_camera_path(session_id, zone_id)
        if os.path.exists(side_path):
            try:
                return cv2.imread(side_path)
            except Exception as e:
                logger.error(f"Error loading side image: {e}")
        return None

    def load_all_zones(self, session_id: str) -> List[CapturedFrames]:
        """
        모든 Zone 이미지 로드.

        Args:
            session_id: 세션 ID

        Returns:
            CapturedFrames 리스트 (활성화된 Zone)
        """
        return [self.load_zone(session_id, zone_id) for zone_id in get_enabled_zones()]

    def check_folder_exists(self, session_id: str) -> bool:
        """
        스냅샷 폴더 존재 여부 확인.

        Args:
            session_id: 세션 ID

        Returns:
            폴더 존재 여부
        """
        folder_path = get_snapshot_folder(session_id)
        return os.path.isdir(folder_path)

    def list_available_images(self, session_id: str) -> dict:
        """
        스냅샷 폴더 내 사용 가능한 이미지 목록.

        Args:
            session_id: 세션 ID

        Returns:
            {
                "top": bool,
                "zones": {zone_id: bool for each enabled zone}
            }
        """
        enabled_zones = get_enabled_zones()
        result = {
            "top": False,
            "zones": {zone_id: False for zone_id in enabled_zones}
        }

        top_path = get_top_camera_path(session_id)
        result["top"] = os.path.exists(top_path)

        for zone_id in enabled_zones:
            side_path = get_side_camera_path(session_id, zone_id)
            result["zones"][zone_id] = os.path.exists(side_path)

        return result
