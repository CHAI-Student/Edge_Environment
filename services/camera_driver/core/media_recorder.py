"""
Media Recorder

이미지 및 영상 저장 모듈

저장 구조:
    {base_path}/{session_id}/
    ├── images/
    │   ├── cam_0/          # Top camera
    │   │   ├── frame_001.jpg
    │   │   └── ...
    │   ├── cam_1/          # Side Zone 0
    │   └── cam_5/          # Side Zone 4
    └── videos/
        ├── cam_0.mp4       # Top camera
        ├── cam_1.mp4
        └── cam_5.mp4

카메라 번호:
    - cam_0: Top camera (손 감지, 전체 Zone 커버)
    - cam_1 ~ cam_5: Side camera (Zone 0 ~ Zone 4)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
import threading
import logging
import time
import os

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
class RecordingConfig:
    """녹화 설정"""
    base_path: str = "./recordings"
    fps: int = 30
    resolution: Tuple[int, int] = (640, 480)  # 캡처 해상도
    save_resolution: Tuple[int, int] = (480, 480)  # 저장 해상도 (크롭 후)
    crop_from_left: bool = True  # True: 왼쪽 기준 크롭 (오른쪽 제거), False: 중앙 크롭
    video_codec: str = "mp4v"  # or "avc1", "XVID"
    jpeg_quality: int = 90
    max_duration: float = 60.0  # 최대 녹화 시간 (초)
    buffer_before_event: float = 2.0  # 이벤트 전 버퍼링 시간 (초)


@dataclass
class RecordingSession:
    """녹화 세션 정보"""
    session_id: str
    base_path: Path
    start_time: float = field(default_factory=time.time)
    cameras: List[int] = field(default_factory=list)
    is_active: bool = True
    frame_counts: Dict[int, int] = field(default_factory=dict)
    video_writers: Dict[int, Any] = field(default_factory=dict)


class MediaRecorder:
    """
    Media Recorder

    이미지 및 영상 저장 관리

    기능:
    - 세션 기반 녹화 (타임스탬프별 폴더)
    - 이미지 저장 (카메라별 폴더)
    - 영상 저장 (MP4)
    - 동시 다중 카메라 지원
    - 프레임 크롭 (640x480 → 480x480, 오른쪽 160px 제거)
    """

    def __init__(self, config: Optional[RecordingConfig] = None):
        """
        초기화

        Args:
            config: 녹화 설정
        """
        self.config = config or RecordingConfig()
        self._sessions: Dict[str, RecordingSession] = {}
        self._lock = threading.Lock()

    def _crop_frame(self, frame: Any) -> Any:
        """
        프레임 크롭 (640x480 → 480x480).

        오른쪽 160px를 제거하고 왼쪽 480px만 유지합니다.

        Args:
            frame: 원본 프레임 (numpy array, H x W x C)

        Returns:
            크롭된 프레임
        """
        if not CV2_AVAILABLE or frame is None:
            return frame

        h, w = frame.shape[:2]
        target_w, target_h = self.config.save_resolution

        # 높이 조정 필요 시
        if h != target_h:
            # 높이 크롭 (중앙 기준)
            if h > target_h:
                start_y = (h - target_h) // 2
                frame = frame[start_y:start_y + target_h, :, :]
                h = target_h

        # 너비 크롭
        if w > target_w:
            if self.config.crop_from_left:
                # 왼쪽 기준 크롭: 왼쪽 target_w 픽셀 유지 (오른쪽 제거)
                frame = frame[:, :target_w, :]
            else:
                # 중앙 기준 크롭
                start_x = (w - target_w) // 2
                frame = frame[:, start_x:start_x + target_w, :]
        elif w < target_w:
            # 너비가 목표보다 작으면 리사이즈
            frame = cv2.resize(frame, (target_w, target_h))

        return frame

    def create_session(
        self,
        cameras: List[int],
        session_id: Optional[str] = None,
    ) -> str:
        """
        녹화 세션 생성

        Args:
            cameras: 녹화할 카메라 ID 목록 (0=Top, 1-5=Zone)
            session_id: 세션 ID (없으면 자동 생성)

        Returns:
            세션 ID (예: "20251106_141029")
        """
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 기본 경로 생성
        base_path = Path(self.config.base_path) / session_id
        images_path = base_path / "images"
        videos_path = base_path / "videos"

        # 디렉토리 생성
        images_path.mkdir(parents=True, exist_ok=True)
        videos_path.mkdir(parents=True, exist_ok=True)

        # 카메라별 이미지 폴더 생성
        for cam_id in cameras:
            cam_images_path = images_path / f"cam_{cam_id}"
            cam_images_path.mkdir(exist_ok=True)

        # 세션 객체 생성
        session = RecordingSession(
            session_id=session_id,
            base_path=base_path,
            cameras=cameras,
            frame_counts={cam_id: 0 for cam_id in cameras},
        )

        with self._lock:
            self._sessions[session_id] = session

        logger.info(f"Recording session created: {session_id}")
        logger.info(f"  - Path: {base_path}")
        logger.info(f"  - Cameras: {cameras}")

        return session_id

    def start_video_recording(self, session_id: str) -> bool:
        """
        영상 녹화 시작 (크롭된 해상도로 저장: 480x480)

        Args:
            session_id: 세션 ID

        Returns:
            시작 성공 여부
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available for video recording")
            return False

        session = self._sessions.get(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return False

        videos_path = session.base_path / "videos"
        fourcc = cv2.VideoWriter_fourcc(*self.config.video_codec)

        for cam_id in session.cameras:
            video_path = videos_path / f"cam_{cam_id}.mp4"
            # 크롭된 해상도로 VideoWriter 생성 (480x480)
            writer = cv2.VideoWriter(
                str(video_path),
                fourcc,
                self.config.fps,
                self.config.save_resolution,
            )
            if writer.isOpened():
                session.video_writers[cam_id] = writer
                logger.info(f"Video writer started: cam_{cam_id} -> {video_path} (resolution: {self.config.save_resolution})")
            else:
                logger.error(f"Failed to create video writer for cam_{cam_id}")

        return len(session.video_writers) > 0

    def stop_video_recording(self, session_id: str) -> Dict[int, str]:
        """
        영상 녹화 중지 및 파일 저장

        Args:
            session_id: 세션 ID

        Returns:
            {camera_id: video_path} 매핑
        """
        session = self._sessions.get(session_id)
        if not session:
            return {}

        video_paths: Dict[int, str] = {}

        for cam_id, writer in session.video_writers.items():
            if writer:
                writer.release()
                video_path = session.base_path / "videos" / f"cam_{cam_id}.mp4"
                video_paths[cam_id] = str(video_path)
                logger.info(f"Video saved: {video_path}")

        session.video_writers.clear()
        return video_paths

    def write_video_frame(
        self,
        session_id: str,
        camera_id: int,
        frame: Any,
    ) -> bool:
        """
        영상에 프레임 기록 (크롭 적용: 640x480 → 480x480)

        Args:
            session_id: 세션 ID
            camera_id: 카메라 ID
            frame: 이미지 프레임 (numpy array)

        Returns:
            기록 성공 여부
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        writer = session.video_writers.get(camera_id)
        if not writer:
            return False

        try:
            # 프레임 크롭 (640x480 → 480x480)
            cropped_frame = self._crop_frame(frame)

            # 해상도가 다르면 리사이즈
            if cropped_frame.shape[:2] != self.config.save_resolution[::-1]:
                cropped_frame = cv2.resize(cropped_frame, self.config.save_resolution)

            writer.write(cropped_frame)
            return True
        except Exception as e:
            logger.error(f"Failed to write video frame: {e}")
            return False

    def save_image(
        self,
        session_id: str,
        camera_id: int,
        frame: Any,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        이미지 저장 (크롭 적용: 640x480 → 480x480)

        오른쪽 160px를 제거하고 480x480 이미지로 저장합니다.

        Args:
            session_id: 세션 ID
            camera_id: 카메라 ID
            frame: 이미지 프레임 (numpy array)
            filename: 파일명 (없으면 자동 생성)

        Returns:
            저장된 파일 경로
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available for image saving")
            return None

        session = self._sessions.get(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return None

        # 프레임 카운트 증가
        frame_num = session.frame_counts.get(camera_id, 0) + 1
        session.frame_counts[camera_id] = frame_num

        # 파일명 생성
        if filename is None:
            filename = f"frame_{frame_num:04d}.jpg"

        # 저장 경로
        image_path = session.base_path / "images" / f"cam_{camera_id}" / filename

        try:
            # 프레임 크롭 (640x480 → 480x480)
            cropped_frame = self._crop_frame(frame)

            # JPEG 품질 설정
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality]
            cv2.imwrite(str(image_path), cropped_frame, encode_params)
            logger.debug(f"Image saved: {image_path} (cropped to {self.config.save_resolution})")
            return str(image_path)
        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            return None

    def save_images_batch(
        self,
        session_id: str,
        frames: Dict[int, Any],
    ) -> Dict[int, str]:
        """
        다중 카메라 이미지 일괄 저장

        Args:
            session_id: 세션 ID
            frames: {camera_id: frame} 딕셔너리

        Returns:
            {camera_id: image_path} 매핑
        """
        results: Dict[int, str] = {}

        for cam_id, frame in frames.items():
            path = self.save_image(session_id, cam_id, frame)
            if path:
                results[cam_id] = path

        return results

    def close_session(self, session_id: str) -> Dict[str, Any]:
        """
        세션 종료 및 정리

        Args:
            session_id: 세션 ID

        Returns:
            세션 정보 (저장된 파일 경로 등)
        """
        session = self._sessions.get(session_id)
        if not session:
            return {}

        # 영상 녹화 중지
        video_paths = self.stop_video_recording(session_id)

        # 세션 정보 수집
        result = {
            "session_id": session_id,
            "base_path": str(session.base_path),
            "duration": time.time() - session.start_time,
            "frame_counts": dict(session.frame_counts),
            "video_paths": video_paths,
            "images_path": str(session.base_path / "images"),
            "videos_path": str(session.base_path / "videos"),
        }

        session.is_active = False

        with self._lock:
            del self._sessions[session_id]

        logger.info(f"Recording session closed: {session_id}")
        return result

    def get_session_paths(self, session_id: str) -> Dict[str, str]:
        """
        세션 경로 정보 조회

        Args:
            session_id: 세션 ID

        Returns:
            경로 정보 딕셔너리
        """
        session = self._sessions.get(session_id)
        if not session:
            return {}

        return {
            "base_path": str(session.base_path),
            "images_path": str(session.base_path / "images"),
            "videos_path": str(session.base_path / "videos"),
        }

    def get_camera_image_path(
        self,
        session_id: str,
        camera_id: int,
    ) -> Optional[str]:
        """
        특정 카메라의 이미지 저장 경로

        Args:
            session_id: 세션 ID
            camera_id: 카메라 ID

        Returns:
            이미지 폴더 경로
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        return str(session.base_path / "images" / f"cam_{camera_id}")

    def get_camera_video_path(
        self,
        session_id: str,
        camera_id: int,
    ) -> Optional[str]:
        """
        특정 카메라의 영상 저장 경로

        Args:
            session_id: 세션 ID
            camera_id: 카메라 ID

        Returns:
            영상 파일 경로
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        return str(session.base_path / "videos" / f"cam_{camera_id}.mp4")

    def list_sessions(self) -> List[Dict[str, Any]]:
        """활성 세션 목록"""
        return [
            {
                "session_id": s.session_id,
                "base_path": str(s.base_path),
                "cameras": s.cameras,
                "frame_counts": dict(s.frame_counts),
                "is_active": s.is_active,
                "duration": time.time() - s.start_time,
            }
            for s in self._sessions.values()
        ]


class EventRecorder:
    """
    이벤트 기반 녹화 관리

    loadcell.change 이벤트 발생 시 이미지/영상 캡처
    """

    def __init__(
        self,
        media_recorder: MediaRecorder,
        camera_manager: Any,
    ):
        """
        초기화

        Args:
            media_recorder: MediaRecorder 인스턴스
            camera_manager: CameraManager 인스턴스
        """
        self.media = media_recorder
        self.cameras = camera_manager
        self._active_session: Optional[str] = None
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start_event_recording(
        self,
        zone_id: int,
        include_top: bool = True,
        record_video: bool = True,
    ) -> str:
        """
        Zone 이벤트 녹화 시작

        Args:
            zone_id: Zone ID (0-4)
            include_top: Top 카메라 포함 여부
            record_video: 영상 녹화 여부

        Returns:
            세션 ID
        """
        # 카메라 목록 결정
        cameras = []
        if include_top:
            cameras.append(0)  # Top camera

        # Zone에 해당하는 Side 카메라 (Zone 0 → cam_1, Zone 1 → cam_2, ...)
        side_camera_id = zone_id + 1
        cameras.append(side_camera_id)

        # 세션 생성
        session_id = self.media.create_session(cameras)
        self._active_session = session_id

        # 영상 녹화 시작
        if record_video:
            self.media.start_video_recording(session_id)
            self._start_video_capture_thread(session_id, cameras)

        logger.info(f"Event recording started for Zone {zone_id}: {session_id}")
        return session_id

    def _start_video_capture_thread(
        self,
        session_id: str,
        cameras: List[int],
    ) -> None:
        """영상 캡처 스레드 시작"""
        self._stop_event.clear()
        self._recording_thread = threading.Thread(
            target=self._video_capture_loop,
            args=(session_id, cameras),
            daemon=True,
        )
        self._recording_thread.start()

    def _video_capture_loop(
        self,
        session_id: str,
        cameras: List[int],
    ) -> None:
        """영상 캡처 루프"""
        interval = 1.0 / self.media.config.fps
        start_time = time.time()

        while not self._stop_event.is_set():
            # 최대 녹화 시간 체크
            if time.time() - start_time > self.media.config.max_duration:
                logger.info("Max recording duration reached")
                break

            # 각 카메라에서 프레임 캡처 및 저장
            for cam_id in cameras:
                frame = self.cameras.get_frame(cam_id)
                if frame is not None:
                    self.media.write_video_frame(session_id, cam_id, frame)

            time.sleep(interval)

    def capture_snapshot(
        self,
        zone_id: Optional[int] = None,
        all_cameras: bool = False,
    ) -> Dict[int, str]:
        """
        스냅샷 캡처

        Args:
            zone_id: Zone ID (None이면 Top만)
            all_cameras: 모든 카메라 캡처

        Returns:
            {camera_id: image_path} 매핑
        """
        if not self._active_session:
            # 임시 세션 생성
            cameras = [0]  # Top
            if zone_id is not None:
                cameras.append(zone_id + 1)
            elif all_cameras:
                cameras = [0, 1, 2, 3, 4, 5]

            session_id = self.media.create_session(cameras)
        else:
            session_id = self._active_session

        # 프레임 캡처
        frames: Dict[int, Any] = {}
        session = self.media._sessions.get(session_id)

        if session:
            for cam_id in session.cameras:
                frame = self.cameras.get_frame(cam_id)
                if frame is not None:
                    frames[cam_id] = frame

        # 이미지 저장
        return self.media.save_images_batch(session_id, frames)

    def stop_event_recording(self) -> Optional[Dict[str, Any]]:
        """
        이벤트 녹화 중지

        Returns:
            세션 정보 (저장된 파일 경로 등)
        """
        if not self._active_session:
            return None

        # 녹화 스레드 중지
        self._stop_event.set()
        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=2.0)

        # 세션 종료
        result = self.media.close_session(self._active_session)
        self._active_session = None

        logger.info(f"Event recording stopped")
        return result

    @property
    def is_recording(self) -> bool:
        return self._active_session is not None
