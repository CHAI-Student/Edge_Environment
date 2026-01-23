"""
Camera Manager

6대 카메라 동시 관리 (Top 1 + Zone 5)

기능:
- 고유 ID 기반 카메라 매핑
- 동적 디바이스 재매핑
- 자동 재연결 (reconnect)
- 헬스 체크
"""

from typing import Any, Dict, List, Optional, Tuple
import logging
import threading
import time

from ..config import (
    settings,
    ZONE_CAMERA_MAP,
    TOP_CAMERA_ID,
    ZONE_CAMERA_IDS,
    ALL_CAMERA_IDS,
    CAMERA_ID_MAPPING,
    save_camera_mapping,
    update_camera_identifier,
    get_physical_device_index,
)
from .camera import ZoneCamera, CameraConfig
from .device_scanner import DeviceScanner, CameraDeviceInfo
from .media_recorder import MediaRecorder, EventRecorder, RecordingConfig

logger = logging.getLogger(__name__)


class CameraManager:
    """
    Camera Manager

    6대 카메라 동시 관리:
    - Camera 0: Top 카메라 (손 감지, 전체 Zone 커버)
    - Camera 1-5: Zone별 전용 Side 카메라

    기능:
    - 고유 ID 기반 카메라 매핑 (USB 시리얼)
    - 동적 디바이스 재매핑 (USB 포트 변경 대응)
    - 자동 재연결 (disconnection 복구)
    - 헬스 체크 (연결 상태 모니터링)
    """

    def __init__(
        self,
        resolution: Optional[Tuple[int, int]] = None,
        fps: Optional[int] = None,
        buffer_size: Optional[int] = None,
        auto_reconnect: bool = True,
    ):
        """
        초기화

        Args:
            resolution: 프레임 해상도
            fps: 목표 FPS
            buffer_size: 프레임 버퍼 크기
            auto_reconnect: 자동 재연결 활성화
        """
        self.resolution = resolution or (settings.resolution_width, settings.resolution_height)
        self.fps = fps or settings.fps
        self.buffer_size = buffer_size or settings.buffer_size
        self.auto_reconnect = auto_reconnect

        # 카메라 객체
        self._cameras: Dict[int, ZoneCamera] = {}
        self._initialized = False
        self._streaming = False

        # 디바이스 스캐너
        self._scanner = DeviceScanner(max_index=settings.max_scan_index)

        # Zone-카메라 인덱스 매핑 (동적)
        self._zone_to_device: Dict[int, int] = dict(ZONE_CAMERA_MAP)
        self._top_device_index: int = TOP_CAMERA_ID

        # 재연결 스레드
        self._reconnect_thread: Optional[threading.Thread] = None
        self._reconnect_running = False
        self._reconnect_lock = threading.Lock()

        # 연결 상태 추적
        self._connection_failures: Dict[int, int] = {}  # camera_id -> failure_count

        # 미디어 레코더
        self._media_recorder: Optional[MediaRecorder] = None
        self._event_recorder: Optional[EventRecorder] = None

    def initialize_all(self) -> Dict[int, bool]:
        """
        모든 카메라 초기화

        물리적 디바이스 인덱스 매핑을 적용하여 카메라를 초기화합니다.
        Nvidia 모드에서는 짝수 인덱스(0, 2, 4, 6, 8, 10)를 사용합니다.

        Returns:
            {camera_id: success} 딕셔너리
        """
        status: Dict[int, bool] = {}

        # Top 카메라
        top_device_index = get_physical_device_index(TOP_CAMERA_ID)
        top_config = CameraConfig(
            camera_id=TOP_CAMERA_ID,
            resolution=self.resolution,
            fps=self.fps,
            buffer_size=self.buffer_size,
            is_top_camera=True,
            device_index=top_device_index,
        )
        top_camera = ZoneCamera(top_config)
        status[TOP_CAMERA_ID] = top_camera.connect()
        self._cameras[TOP_CAMERA_ID] = top_camera
        logger.info(f"Top camera: logical_id={TOP_CAMERA_ID}, device_index={top_device_index}")

        # Zone 카메라
        for zone_id, camera_id in ZONE_CAMERA_MAP.items():
            device_index = get_physical_device_index(camera_id)
            zone_config = CameraConfig(
                camera_id=camera_id,
                resolution=self.resolution,
                fps=self.fps,
                buffer_size=self.buffer_size,
                is_top_camera=False,
                zone_id=zone_id,
                device_index=device_index,
            )
            zone_camera = ZoneCamera(zone_config)
            status[camera_id] = zone_camera.connect()
            self._cameras[camera_id] = zone_camera
            logger.info(f"Zone {zone_id} camera: logical_id={camera_id}, device_index={device_index}")

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

    # =========================================================================
    # 디바이스 스캔 및 동적 매핑
    # =========================================================================

    def scan_devices(self) -> List[CameraDeviceInfo]:
        """
        시스템의 모든 카메라 디바이스 스캔.

        Returns:
            CameraDeviceInfo 리스트
        """
        return self._scanner.scan_all_devices(refresh=True)

    def rebuild_mapping(self) -> Dict[str, int]:
        """
        고유 ID 기반 카메라 매핑 재구성.

        USB 포트 변경 등으로 디바이스 인덱스가 변경된 경우
        설정된 고유 ID를 기반으로 매핑을 재구성합니다.

        Returns:
            {zone_key: device_index} 매핑 결과
        """
        logger.info("Rebuilding camera mapping...")

        # 디바이스 스캔
        devices = self._scanner.scan_all_devices(refresh=True)
        logger.info(f"Found {len(devices)} camera devices")

        # 설정 기반 매핑 재구성
        new_mapping = self._scanner.rebuild_mapping(CAMERA_ID_MAPPING)

        # Top 카메라 매핑
        top_config = CAMERA_ID_MAPPING.get("top", {})
        if top_config.get("identifier"):
            idx = self._scanner.find_by_identifier(top_config["identifier"])
            if idx is not None:
                self._top_device_index = idx
                logger.info(f"Top camera mapped to device {idx}")
            else:
                self._top_device_index = top_config.get("fallback_index", TOP_CAMERA_ID)
                logger.warning(f"Top camera using fallback index {self._top_device_index}")
        else:
            self._top_device_index = top_config.get("fallback_index", TOP_CAMERA_ID)

        # Zone 카메라 매핑
        for zone_key, device_idx in new_mapping.items():
            if zone_key.startswith("zone_"):
                try:
                    zone_id = int(zone_key.split("_")[1])
                    self._zone_to_device[zone_id] = device_idx
                except (ValueError, IndexError):
                    pass

        logger.info(f"Mapping rebuilt: top={self._top_device_index}, zones={self._zone_to_device}")
        return new_mapping

    def learn_device_identifiers(self) -> Dict[str, str]:
        """
        현재 연결된 카메라의 고유 ID 학습.

        현재 인덱스 기반으로 연결된 카메라의 고유 ID를 추출하여
        설정에 저장합니다. 초기 설정 시 사용합니다.

        Returns:
            {zone_key: identifier} 매핑
        """
        devices = self._scanner.scan_all_devices(refresh=True)
        learned: Dict[str, str] = {}

        for device in devices:
            if not device.identifier:
                continue

            # Top 카메라
            if device.device_index == TOP_CAMERA_ID:
                update_camera_identifier("top", device.identifier)
                learned["top"] = device.identifier

            # Zone 카메라
            for zone_id, cam_id in ZONE_CAMERA_MAP.items():
                if device.device_index == cam_id:
                    zone_key = f"zone_{zone_id}"
                    update_camera_identifier(zone_key, device.identifier)
                    learned[zone_key] = device.identifier
                    break

        # 설정 파일 저장
        if learned:
            save_camera_mapping()
            logger.info(f"Learned {len(learned)} device identifiers")

        return learned

    # =========================================================================
    # 자동 재연결
    # =========================================================================

    def start_reconnect_monitor(self) -> None:
        """자동 재연결 모니터 시작."""
        if not self.auto_reconnect:
            return

        if self._reconnect_running:
            return

        self._reconnect_running = True
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="CameraReconnect",
        )
        self._reconnect_thread.start()
        logger.info("Camera reconnect monitor started")

    def stop_reconnect_monitor(self) -> None:
        """자동 재연결 모니터 중지."""
        self._reconnect_running = False
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=2.0)
        logger.info("Camera reconnect monitor stopped")

    def _reconnect_loop(self) -> None:
        """재연결 모니터링 루프."""
        while self._reconnect_running:
            try:
                self._check_and_reconnect()
            except Exception as e:
                logger.error(f"Reconnect loop error: {e}")

            time.sleep(settings.reconnect_interval)

    def _check_and_reconnect(self) -> None:
        """연결 상태 확인 및 재연결 시도."""
        with self._reconnect_lock:
            for camera_id, camera in list(self._cameras.items()):
                if not camera.is_connected:
                    # 실패 횟수 증가
                    self._connection_failures[camera_id] = \
                        self._connection_failures.get(camera_id, 0) + 1

                    failure_count = self._connection_failures[camera_id]

                    if failure_count > settings.max_reconnect_attempts:
                        logger.error(
                            f"Camera {camera_id}: Max reconnect attempts exceeded"
                        )
                        continue

                    logger.info(
                        f"Camera {camera_id}: Attempting reconnect "
                        f"({failure_count}/{settings.max_reconnect_attempts})"
                    )

                    # 재연결 시도
                    if self._try_reconnect_camera(camera_id):
                        self._connection_failures[camera_id] = 0
                        logger.info(f"Camera {camera_id}: Reconnected successfully")
                    else:
                        # 매핑 재구성 시도 (USB 포트 변경 가능성)
                        if failure_count >= 3:
                            logger.info("Attempting to rebuild camera mapping...")
                            self.rebuild_mapping()

    def _try_reconnect_camera(self, camera_id: int) -> bool:
        """
        단일 카메라 재연결 시도.

        Args:
            camera_id: 카메라 ID

        Returns:
            재연결 성공 여부
        """
        if camera_id not in self._cameras:
            return False

        camera = self._cameras[camera_id]

        # 기존 연결 해제
        camera.disconnect()

        # 재연결
        if camera.connect():
            if self._streaming:
                camera.start_streaming()
            return True

        return False

    def reconnect_camera(self, camera_id: int) -> bool:
        """
        특정 카메라 수동 재연결.

        Args:
            camera_id: 카메라 ID

        Returns:
            재연결 성공 여부
        """
        with self._reconnect_lock:
            if self._try_reconnect_camera(camera_id):
                self._connection_failures[camera_id] = 0
                return True
            return False

    # =========================================================================
    # 헬스 체크
    # =========================================================================

    def health_check(self) -> Dict[int, bool]:
        """
        모든 카메라 헬스 체크.

        Returns:
            {camera_id: is_healthy} 딕셔너리
        """
        health: Dict[int, bool] = {}

        for camera_id, camera in self._cameras.items():
            # 연결 상태 확인
            if not camera.is_connected:
                health[camera_id] = False
                continue

            # 프레임 캡처 가능 여부 확인
            frame = camera.get_frame()
            health[camera_id] = frame is not None

        return health

    def get_detailed_status(self) -> Dict[str, Any]:
        """
        상세 상태 조회 (디바이스 정보 포함).

        Returns:
            상세 상태 딕셔너리
        """
        devices = self._scanner.scan_all_devices()

        return {
            "initialized": self._initialized,
            "streaming": self._streaming,
            "reconnect_monitor_active": self._reconnect_running,
            "top_device_index": self._top_device_index,
            "zone_mapping": dict(self._zone_to_device),
            "cameras": [
                {
                    **camera.get_status(),
                    "failure_count": self._connection_failures.get(camera.camera_id, 0),
                }
                for camera in self._cameras.values()
            ],
            "available_devices": [
                {
                    "index": d.device_index,
                    "name": d.name,
                    "identifier": d.identifier,
                    "available": d.is_available,
                }
                for d in devices
            ],
        }

    # =========================================================================
    # 미디어 녹화 기능
    # =========================================================================

    def init_media_recorder(
        self,
        base_path: str = "./recordings",
        fps: Optional[int] = None,
    ) -> None:
        """
        미디어 레코더 초기화.

        Args:
            base_path: 녹화 저장 기본 경로
            fps: 영상 FPS
        """
        config = RecordingConfig(
            base_path=base_path,
            fps=fps or self.fps,
            resolution=self.resolution,
        )
        self._media_recorder = MediaRecorder(config)
        self._event_recorder = EventRecorder(self._media_recorder, self)
        logger.info(f"Media recorder initialized: {base_path}")

    def start_recording(
        self,
        zone_id: Optional[int] = None,
        cameras: Optional[List[int]] = None,
        include_top: bool = True,
        record_video: bool = True,
    ) -> Optional[str]:
        """
        녹화 시작.

        Args:
            zone_id: Zone ID (특정 Zone만 녹화)
            cameras: 카메라 ID 목록 (직접 지정)
            include_top: Top 카메라 포함 여부
            record_video: 영상 녹화 여부

        Returns:
            세션 ID
        """
        if not self._media_recorder:
            self.init_media_recorder()

        if self._event_recorder and zone_id is not None:
            return self._event_recorder.start_event_recording(
                zone_id=zone_id,
                include_top=include_top,
                record_video=record_video,
            )

        # 카메라 목록 결정
        if cameras is None:
            cameras = []
            if include_top:
                cameras.append(TOP_CAMERA_ID)
            if zone_id is not None:
                cameras.append(zone_id + 1)  # Zone 0 → cam_1
            else:
                cameras.extend(ZONE_CAMERA_IDS)

        session_id = self._media_recorder.create_session(cameras)

        if record_video:
            self._media_recorder.start_video_recording(session_id)

        return session_id

    def stop_recording(self) -> Optional[Dict[str, Any]]:
        """
        녹화 중지.

        Returns:
            세션 정보
        """
        if self._event_recorder:
            return self._event_recorder.stop_event_recording()
        return None

    def capture_snapshot(
        self,
        session_id: Optional[str] = None,
        zone_id: Optional[int] = None,
        all_cameras: bool = False,
    ) -> Dict[int, str]:
        """
        스냅샷 캡처.

        Args:
            session_id: 기존 세션에 저장 (없으면 새 세션 생성)
            zone_id: Zone ID (None이면 Top만)
            all_cameras: 모든 카메라 캡처

        Returns:
            {camera_id: image_path} 매핑
        """
        if not self._media_recorder:
            self.init_media_recorder()

        # 카메라 목록 결정
        cameras = []
        if all_cameras:
            cameras = ALL_CAMERA_IDS.copy()
        elif zone_id is not None:
            cameras = [TOP_CAMERA_ID, zone_id + 1]
        else:
            cameras = [TOP_CAMERA_ID]

        # 세션이 없으면 생성
        if not session_id:
            session_id = self._media_recorder.create_session(cameras)

        # 프레임 캡처
        frames: Dict[int, Any] = {}
        for cam_id in cameras:
            if cam_id in self._cameras:
                frame = self._cameras[cam_id].get_frame()
                if frame is not None:
                    frames[cam_id] = frame

        # 이미지 저장
        return self._media_recorder.save_images_batch(session_id, frames)

    def write_video_frames(self, session_id: str) -> int:
        """
        현재 모든 카메라 프레임을 영상에 기록.

        Args:
            session_id: 세션 ID

        Returns:
            기록된 프레임 수
        """
        if not self._media_recorder:
            return 0

        session = self._media_recorder._sessions.get(session_id)
        if not session:
            return 0

        count = 0
        for cam_id in session.cameras:
            if cam_id in self._cameras:
                frame = self._cameras[cam_id].get_frame()
                if frame is not None:
                    if self._media_recorder.write_video_frame(session_id, cam_id, frame):
                        count += 1

        return count

    def get_recording_paths(self, session_id: str) -> Dict[str, str]:
        """
        녹화 세션 경로 조회.

        Args:
            session_id: 세션 ID

        Returns:
            경로 정보
        """
        if not self._media_recorder:
            return {}

        return self._media_recorder.get_session_paths(session_id)

    def close_recording_session(self, session_id: str) -> Dict[str, Any]:
        """
        녹화 세션 종료.

        Args:
            session_id: 세션 ID

        Returns:
            세션 정보
        """
        if not self._media_recorder:
            return {}

        return self._media_recorder.close_session(session_id)

    @property
    def is_recording(self) -> bool:
        """녹화 중 여부"""
        if self._event_recorder:
            return self._event_recorder.is_recording
        return False
