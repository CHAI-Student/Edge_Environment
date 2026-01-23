"""
Zone Camera

개별 카메라 핸들러: 스레드 기반 프레임 캡처 및 버퍼링
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Any
from collections import deque
import threading
import time
import logging

try:
    import cv2
    import numpy as np

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    np = None

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """카메라 설정"""

    camera_id: int  # 논리적 카메라 ID (0-5)
    resolution: Tuple[int, int] = (640, 480)
    fps: int = 30
    buffer_size: int = 60
    is_top_camera: bool = False
    zone_id: Optional[int] = None
    device_index: Optional[int] = None  # 물리적 디바이스 인덱스 (None이면 camera_id 사용)


class ZoneCamera:
    """
    개별 카메라 핸들러

    스레드 기반 프레임 캡처 및 버퍼링
    """

    def __init__(self, config: CameraConfig):
        """
        초기화

        Args:
            config: 카메라 설정
        """
        self.config = config
        self._cap: Optional[Any] = None
        self._frame_buffer: deque = deque(maxlen=config.buffer_size)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_frame: Optional[Any] = None
        self._last_frame_time: float = 0.0
        self._frame_count = 0
        self._active = False  # 활성 상태

    @property
    def camera_id(self) -> int:
        return self.config.camera_id

    @property
    def is_connected(self) -> bool:
        return self._cap is not None and self._cap.isOpened() if CV2_AVAILABLE else False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def device_index(self) -> int:
        """물리적 디바이스 인덱스"""
        return self.config.device_index if self.config.device_index is not None else self.config.camera_id

    def connect(self) -> bool:
        """카메라 연결"""
        if not CV2_AVAILABLE:
            logger.warning(f"Camera {self.camera_id}: OpenCV not available")
            return False

        try:
            # 물리적 디바이스 인덱스 사용
            device_idx = self.device_index
            logger.info(f"Camera {self.camera_id}: Opening device index {device_idx}")

            self._cap = cv2.VideoCapture(device_idx)
            if not self._cap.isOpened():
                logger.error(f"Camera {self.camera_id}: Failed to open device {device_idx}")
                return False

            # 해상도 설정
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.resolution[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.resolution[1])
            self._cap.set(cv2.CAP_PROP_FPS, self.config.fps)

            logger.info(f"Camera {self.camera_id}: Connected to device {device_idx}")
            return True

        except Exception as e:
            logger.error(f"Camera {self.camera_id}: Connection error - {e}")
            return False

    def disconnect(self) -> None:
        """카메라 연결 해제"""
        self.stop_streaming()
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info(f"Camera {self.camera_id}: Disconnected")

    def start_streaming(self) -> None:
        """프레임 캡처 시작"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Camera {self.camera_id}: Streaming started")

    def stop_streaming(self) -> None:
        """프레임 캡처 중지"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info(f"Camera {self.camera_id}: Streaming stopped")

    def _capture_loop(self) -> None:
        """프레임 캡처 루프"""
        while self._running and self._cap and self._cap.isOpened():
            try:
                ret, frame = self._cap.read()
                if ret:
                    current_time = time.time()
                    with self._lock:
                        self._last_frame = frame
                        self._last_frame_time = current_time
                        if self._active:
                            self._frame_buffer.append((current_time, frame))
                        self._frame_count += 1

                # FPS 제한
                time.sleep(1.0 / self.config.fps)

            except Exception as e:
                logger.error(f"Camera {self.camera_id}: Capture error - {e}")
                time.sleep(0.1)

    def get_frame(self) -> Optional[Any]:
        """최신 프레임 가져오기"""
        with self._lock:
            return self._last_frame.copy() if self._last_frame is not None else None

    def get_frame_with_timestamp(self) -> Tuple[Optional[Any], float]:
        """최신 프레임과 타임스탬프 가져오기"""
        with self._lock:
            if self._last_frame is not None:
                return (self._last_frame.copy(), self._last_frame_time)
            return (None, 0.0)

    def get_buffered_frames(
        self, lookback_time: float = 1.0
    ) -> List[Tuple[float, Any]]:
        """
        버퍼된 프레임 가져오기

        Args:
            lookback_time: 조회할 과거 시간 (초)

        Returns:
            [(timestamp, frame), ...] 리스트
        """
        cutoff_time = time.time() - lookback_time
        with self._lock:
            return [
                (ts, frame.copy()) for ts, frame in self._frame_buffer if ts >= cutoff_time
            ]

    def activate(self) -> None:
        """활성화 (버퍼링 시작)"""
        self._active = True
        logger.debug(f"Camera {self.camera_id}: Activated")

    def deactivate(self) -> None:
        """비활성화 (버퍼링 중지)"""
        self._active = False
        with self._lock:
            self._frame_buffer.clear()
        logger.debug(f"Camera {self.camera_id}: Deactivated")

    def clear_buffer(self) -> None:
        """버퍼 비우기"""
        with self._lock:
            self._frame_buffer.clear()

    def get_status(self) -> dict:
        """상태 조회"""
        return {
            "camera_id": self.camera_id,
            "device_index": self.device_index,
            "connected": self.is_connected,
            "running": self.is_running,
            "active": self.is_active,
            "is_top_camera": self.config.is_top_camera,
            "zone_id": self.config.zone_id,
            "frame_count": self._frame_count,
        }
