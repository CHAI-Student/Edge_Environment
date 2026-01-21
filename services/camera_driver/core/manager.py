"""
Camera Manager

6대 카메라 동시 관리 (Top 1 + Zone 5)
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

from ..config import (
    settings,
    ZONE_CAMERA_MAP,
    TOP_CAMERA_ID,
    ZONE_CAMERA_IDS,
    ALL_CAMERA_IDS,
)
from .camera import ZoneCamera, CameraConfig

logger = logging.getLogger(__name__)


class CameraManager:
    """
    Camera Manager

    6대 카메라 동시 관리:
    - Camera 0: Top 카메라 (손 감지, 전체 Zone 커버)
    - Camera 1-5: Zone별 전용 Side 카메라
    """

    def __init__(
        self,
        resolution: Optional[Tuple[int, int]] = None,
        fps: Optional[int] = None,
        buffer_size: Optional[int] = None,
    ):
        """
        초기화

        Args:
            resolution: 프레임 해상도
            fps: 목표 FPS
            buffer_size: 프레임 버퍼 크기
        """
        self.resolution = resolution or (settings.resolution_width, settings.resolution_height)
        self.fps = fps or settings.fps
        self.buffer_size = buffer_size or settings.buffer_size

        # 카메라 객체
        self._cameras: Dict[int, ZoneCamera] = {}
        self._initialized = False
        self._streaming = False

    def initialize_all(self) -> Dict[int, bool]:
        """
        모든 카메라 초기화

        Returns:
            {camera_id: success} 딕셔너리
        """
        status: Dict[int, bool] = {}

        # Top 카메라
        top_config = CameraConfig(
            camera_id=TOP_CAMERA_ID,
            resolution=self.resolution,
            fps=self.fps,
            buffer_size=self.buffer_size,
            is_top_camera=True,
        )
        top_camera = ZoneCamera(top_config)
        status[TOP_CAMERA_ID] = top_camera.connect()
        self._cameras[TOP_CAMERA_ID] = top_camera

        # Zone 카메라
        for zone_id, camera_id in ZONE_CAMERA_MAP.items():
            zone_config = CameraConfig(
                camera_id=camera_id,
                resolution=self.resolution,
                fps=self.fps,
                buffer_size=self.buffer_size,
                is_top_camera=False,
                zone_id=zone_id,
            )
            zone_camera = ZoneCamera(zone_config)
            status[camera_id] = zone_camera.connect()
            self._cameras[camera_id] = zone_camera

        self._initialized = True
        connected_count = sum(status.values())
        logger.info(f"CameraManager: {connected_count}/{len(status)} cameras connected")

        return status

    def start_streaming(self) -> None:
        """모든 카메라 스트리밍 시작"""
        for camera in self._cameras.values():
            if camera.is_connected:
                camera.start_streaming()

        # Top 카메라는 항상 활성화
        if TOP_CAMERA_ID in self._cameras:
            self._cameras[TOP_CAMERA_ID].activate()

        self._streaming = True
        logger.info("CameraManager: Streaming started")

    def stop_streaming(self) -> None:
        """모든 카메라 스트리밍 중지"""
        for camera in self._cameras.values():
            camera.stop_streaming()
        self._streaming = False
        logger.info("CameraManager: Streaming stopped")

    def release_all(self) -> None:
        """모든 카메라 리소스 해제"""
        for camera in self._cameras.values():
            camera.disconnect()
        self._cameras.clear()
        self._initialized = False
        self._streaming = False
        logger.info("CameraManager: All cameras released")

    def get_frame(self, camera_id: int) -> Optional[Any]:
        """특정 카메라 프레임 가져오기"""
        if camera_id in self._cameras:
            return self._cameras[camera_id].get_frame()
        return None

    def get_frame_with_timestamp(
        self, camera_id: int
    ) -> Tuple[Optional[Any], float]:
        """특정 카메라 프레임과 타임스탬프 가져오기"""
        if camera_id in self._cameras:
            return self._cameras[camera_id].get_frame_with_timestamp()
        return (None, 0.0)

    def get_zone_frames(
        self,
        zone_id: int,
        include_top: bool = True,
    ) -> Tuple[Optional[Any], Optional[Any]]:
        """
        Zone 프레임 가져오기

        Args:
            zone_id: Zone ID (0-4)
            include_top: Top 카메라 프레임 포함 여부

        Returns:
            (zone_camera_frame, top_camera_frame) 튜플
        """
        zone_frame = None
        top_frame = None

        # Zone 카메라
        camera_id = ZONE_CAMERA_MAP.get(zone_id)
        if camera_id and camera_id in self._cameras:
            zone_frame = self._cameras[camera_id].get_frame()

        # Top 카메라
        if include_top and TOP_CAMERA_ID in self._cameras:
            top_frame = self._cameras[TOP_CAMERA_ID].get_frame()

        return (zone_frame, top_frame)

    def get_top_frame(self) -> Optional[Any]:
        """Top 카메라 프레임"""
        if TOP_CAMERA_ID in self._cameras:
            return self._cameras[TOP_CAMERA_ID].get_frame()
        return None

    def get_zone_buffered_frames(
        self,
        zone_id: int,
        lookback_time: float = 1.0,
    ) -> List[Tuple[float, Any]]:
        """Zone 카메라 버퍼된 프레임"""
        camera_id = ZONE_CAMERA_MAP.get(zone_id)
        if camera_id and camera_id in self._cameras:
            return self._cameras[camera_id].get_buffered_frames(lookback_time)
        return []

    def activate_zone_camera(self, zone_id: int) -> None:
        """Zone 카메라 활성화"""
        camera_id = ZONE_CAMERA_MAP.get(zone_id)
        if camera_id and camera_id in self._cameras:
            self._cameras[camera_id].activate()
            logger.info(f"Zone {zone_id} camera activated")

    def deactivate_zone_camera(self, zone_id: int) -> None:
        """Zone 카메라 비활성화"""
        camera_id = ZONE_CAMERA_MAP.get(zone_id)
        if camera_id and camera_id in self._cameras:
            self._cameras[camera_id].deactivate()
            logger.info(f"Zone {zone_id} camera deactivated")

    def get_camera(self, camera_id: int) -> Optional[ZoneCamera]:
        """카메라 객체 가져오기"""
        return self._cameras.get(camera_id)

    def get_status(self) -> Dict[str, Any]:
        """상태 조회"""
        return {
            "initialized": self._initialized,
            "streaming": self._streaming,
            "cameras": [
                camera.get_status() for camera in self._cameras.values()
            ],
        }

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def connected_count(self) -> int:
        return sum(1 for c in self._cameras.values() if c.is_connected)
