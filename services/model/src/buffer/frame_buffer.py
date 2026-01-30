"""
Frame Buffer for session-based image storage.

Node.js에서 POST /api/frame으로 전송된 이미지를 메모리에 저장하고,
POST /api/judge 호출 시 해당 세션의 이미지를 조회합니다.
"""

import time
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FrameData:
    """단일 프레임 데이터."""

    frame_id: str
    zone_id: int
    camera_id: int  # 0=top, 1-5=side
    image: np.ndarray  # HWC, BGR format
    timestamp: float = field(default_factory=time.time)
    width: int = 0
    height: int = 0
    format: str = "bgr"  # "bgr" or "rgb"

    def __post_init__(self):
        if self.image is not None and len(self.image.shape) == 3:
            self.height, self.width = self.image.shape[:2]


class FrameBuffer:
    """
    세션별 이미지 프레임 버퍼.

    구조:
        _frames[session_id][zone_id][camera_id] = FrameData

    TTL 기반 자동 정리 지원.
    """

    def __init__(
        self,
        ttl_seconds: float = 30.0,
        max_sessions: int = 100,
    ):
        """
        FrameBuffer 초기화.

        Args:
            ttl_seconds: 세션 TTL (기본 30초)
            max_sessions: 최대 세션 수 (기본 100)
        """
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions

        # {session_id: {zone_id: {camera_id: FrameData}}}
        self._frames: Dict[str, Dict[int, Dict[int, FrameData]]] = {}

        # {session_id: last_access_timestamp}
        self._session_timestamps: Dict[str, float] = {}

        self._lock = threading.Lock()

        logger.info(f"FrameBuffer initialized: ttl={ttl_seconds}s, max_sessions={max_sessions}")

    def add_frame(
        self,
        session_id: str,
        zone_id: int,
        camera_id: int,
        image: np.ndarray,
        format: str = "bgr",
    ) -> str:
        """
        프레임 추가.

        Args:
            session_id: 세션 ID
            zone_id: Zone ID (0-4)
            camera_id: Camera ID (0=top, 1-5=side)
            image: numpy 배열 (HWC)
            format: 이미지 형식 ("bgr" 또는 "rgb")

        Returns:
            frame_id: 생성된 프레임 ID
        """
        frame_id = f"f_{uuid.uuid4().hex[:12]}"

        # RGB -> BGR 변환 (필요 시)
        if format.lower() == "rgb":
            image = image[:, :, ::-1].copy()

        frame_data = FrameData(
            frame_id=frame_id,
            zone_id=zone_id,
            camera_id=camera_id,
            image=image,
            format="bgr",  # 저장 형식은 항상 BGR
        )

        with self._lock:
            # TTL 초과 세션 정리
            self._cleanup_expired_sessions()

            # 최대 세션 수 초과 시 가장 오래된 세션 제거
            if len(self._frames) >= self.max_sessions:
                self._remove_oldest_session()

            # 세션 초기화
            if session_id not in self._frames:
                self._frames[session_id] = {}

            if zone_id not in self._frames[session_id]:
                self._frames[session_id][zone_id] = {}

            # 프레임 저장
            self._frames[session_id][zone_id][camera_id] = frame_data
            self._session_timestamps[session_id] = time.time()

        logger.debug(
            f"Frame added: session={session_id}, zone={zone_id}, "
            f"camera={camera_id}, frame_id={frame_id}, "
            f"shape={image.shape}"
        )

        return frame_id

    def get_frames(
        self,
        session_id: str,
        zone_id: int,
    ) -> Dict[int, FrameData]:
        """
        Zone의 모든 프레임 반환.

        Args:
            session_id: 세션 ID
            zone_id: Zone ID

        Returns:
            {camera_id: FrameData} 딕셔너리
        """
        with self._lock:
            if session_id not in self._frames:
                logger.warning(f"Session not found: {session_id}")
                return {}

            if zone_id not in self._frames[session_id]:
                logger.warning(f"Zone not found: session={session_id}, zone={zone_id}")
                return {}

            # 타임스탬프 갱신
            self._session_timestamps[session_id] = time.time()

            return self._frames[session_id][zone_id].copy()

    def get_all_session_frames(
        self,
        session_id: str,
    ) -> Dict[int, Dict[int, FrameData]]:
        """
        세션의 모든 프레임 반환.

        Args:
            session_id: 세션 ID

        Returns:
            {zone_id: {camera_id: FrameData}} 딕셔너리
        """
        with self._lock:
            if session_id not in self._frames:
                logger.warning(f"Session not found: {session_id}")
                return {}

            # 타임스탬프 갱신
            self._session_timestamps[session_id] = time.time()

            return {
                zone_id: cameras.copy()
                for zone_id, cameras in self._frames[session_id].items()
            }

    def get_frame_count(self, session_id: str, zone_id: Optional[int] = None) -> int:
        """
        프레임 수 반환.

        Args:
            session_id: 세션 ID
            zone_id: Zone ID (None이면 전체)

        Returns:
            프레임 수
        """
        with self._lock:
            if session_id not in self._frames:
                return 0

            if zone_id is not None:
                if zone_id not in self._frames[session_id]:
                    return 0
                return len(self._frames[session_id][zone_id])

            return sum(
                len(cameras)
                for cameras in self._frames[session_id].values()
            )

    def clear_session(self, session_id: str) -> bool:
        """
        세션 정리.

        Args:
            session_id: 세션 ID

        Returns:
            성공 여부
        """
        with self._lock:
            if session_id in self._frames:
                del self._frames[session_id]
                self._session_timestamps.pop(session_id, None)
                logger.debug(f"Session cleared: {session_id}")
                return True
            return False

    def clear_all(self):
        """모든 세션 정리."""
        with self._lock:
            self._frames.clear()
            self._session_timestamps.clear()
            logger.info("All sessions cleared")

    def _cleanup_expired_sessions(self):
        """TTL 초과 세션 정리 (lock 내에서 호출)."""
        current_time = time.time()
        expired_sessions = [
            session_id
            for session_id, ts in self._session_timestamps.items()
            if current_time - ts > self.ttl_seconds
        ]

        for session_id in expired_sessions:
            del self._frames[session_id]
            del self._session_timestamps[session_id]
            logger.debug(f"Expired session removed: {session_id}")

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

    def _remove_oldest_session(self):
        """가장 오래된 세션 제거 (lock 내에서 호출)."""
        if not self._session_timestamps:
            return

        oldest_session = min(
            self._session_timestamps.keys(),
            key=lambda k: self._session_timestamps[k]
        )

        del self._frames[oldest_session]
        del self._session_timestamps[oldest_session]
        logger.warning(f"Oldest session removed (max reached): {oldest_session}")

    @property
    def session_count(self) -> int:
        """현재 세션 수."""
        with self._lock:
            return len(self._frames)

    @property
    def total_frame_count(self) -> int:
        """전체 프레임 수."""
        with self._lock:
            return sum(
                len(cameras)
                for session in self._frames.values()
                for cameras in session.values()
            )

    def get_stats(self) -> dict:
        """버퍼 통계 반환."""
        with self._lock:
            return {
                "session_count": len(self._frames),
                "total_frames": self.total_frame_count,
                "ttl_seconds": self.ttl_seconds,
                "max_sessions": self.max_sessions,
            }
