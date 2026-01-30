"""
Camera Manager

카메라 동시 관리 (Top 1 + 활성화된 Zone 카메라)

기능:
- 고유 ID 기반 카메라 매핑
- 동적 디바이스 재매핑
- 자동 재연결 (reconnect)
- 헬스 체크
- Zone 활성화/비활성화 지원
"""

from typing import Any, Dict, List, Optional, Tuple
import logging
import threading
import time

from core.config import (
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

    활성화된 카메라 동시 관리:
    - Camera 0: Top 카메라 (손 감지, 전체 Zone 커버)
    - Camera 1-N: 활성화된 Zone별 전용 Side 카메라

    활성화할 Zone 개수는 다음 방법으로 설정:
    - config/zone_mapping.json의 enabled 필드
    - ENABLED_ZONE_COUNT 환경변수 (우선순위 높음)

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

        # 초기화 중 상태 추적 (중복 초기화 방지)
        self._initializing = False
        self._init_lock = threading.Lock()

        # 연속 촬영 상태
        self._continuous_capture_active = False
        self._continuous_capture_thread: Optional[threading.Thread] = None
        self._continuous_capture_stop_event = threading.Event()
        self._continuous_capture_session_id: Optional[str] = None
        self._continuous_capture_interval = 0.5  # 기본 0.5초 간격

        # Top 카메라 영상 전용 녹화 상태
        self._top_video_session_id: Optional[str] = None
        self._top_video_stop_event = threading.Event()
        self._top_video_thread: Optional[threading.Thread] = None

    def initialize_all(self) -> Dict[int, bool]:
        """
        활성화된 카메라 초기화

        물리적 디바이스 인덱스 매핑을 적용하여 카메라를 초기화합니다.
        Nvidia 모드에서는 짝수 인덱스(0, 2, 4, 6, 8, 10)를 사용합니다.

        활성화된 Zone만 초기화됩니다 (zone_mapping.json의 enabled 또는
        ENABLED_ZONE_COUNT 환경변수 기반).

        Returns:
            {camera_id: success} 딕셔너리
        """
        # 이미 초기화되었으면 현재 상태 반환
        if self._initialized:
            logger.info("CameraManager already initialized, returning current status")
            return {cam_id: cam.is_connected for cam_id, cam in self._cameras.items()}

        # 초기화 중이면 대기 (최대 10초)
        with self._init_lock:
            if self._initializing:
                logger.info("Camera initialization already in progress, waiting...")
                # 락을 해제하고 초기화 완료 대기
                pass

            if self._initialized:
                return {cam_id: cam.is_connected for cam_id, cam in self._cameras.items()}

            self._initializing = True

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

        # 활성화된 Zone 카메라만 초기화
        enabled_zones = list(ZONE_CAMERA_MAP.keys())
        logger.info(f"Initializing cameras for enabled zones: {enabled_zones}")

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
        self._initializing = False
        connected_count = sum(status.values())
        total_expected = 1 + len(ZONE_CAMERA_MAP)  # Top + enabled zones
        logger.info(f"CameraManager: {connected_count}/{total_expected} cameras connected (enabled zones: {enabled_zones})")

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
        base_path: Optional[str] = None,
        fps: Optional[int] = None,
    ) -> None:
        """
        미디어 레코더 초기화.

        Args:
            base_path: 녹화 저장 기본 경로 (None이면 settings.media_base_path 사용)
            fps: 영상 FPS
        """
        # settings.media_base_path 사용 (기본값: "data/")
        actual_base_path = base_path or settings.media_base_path or "data/"
        config = RecordingConfig(
            base_path=actual_base_path,
            fps=fps or self.fps,
            resolution=self.resolution,
            save_resolution=(settings.save_width, settings.save_height),
            crop_from_left=settings.crop_from_left,
        )
        self._media_recorder = MediaRecorder(config)
        self._event_recorder = EventRecorder(self._media_recorder, self)
        logger.info(f"Media recorder initialized: {base_path} (save_resolution: {config.save_resolution}, crop_from_left: {config.crop_from_left})")

    def start_recording(
        self,
        zone_id: Optional[int] = None,
        cameras: Optional[List[int]] = None,
        include_top: bool = True,
        record_video: bool = True,
        use_base_path_directly: bool = False,
    ) -> Optional[str]:
        """
        녹화 시작.

        Args:
            zone_id: Zone ID (특정 Zone만 녹화)
            cameras: 카메라 ID 목록 (직접 지정)
            include_top: Top 카메라 포함 여부
            record_video: 영상 녹화 여부
            use_base_path_directly: True면 Node.js가 전체 경로를 지정한 경우
                                    (base_path를 직접 세션 경로로 사용)

        Returns:
            세션 ID
        """
        if not self._media_recorder:
            self.init_media_recorder()

        # Node.js가 직접 경로를 지정한 경우 EventRecorder 우회
        # (EventRecorder는 use_base_path_directly를 지원하지 않음)
        if self._event_recorder and zone_id is not None and not use_base_path_directly:
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

        session_id = self._media_recorder.create_session(
            cameras,
            use_base_path_directly=use_base_path_directly,
        )

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
        base_path: Optional[str] = None,
    ) -> Dict[int, str]:
        """
        스냅샷 캡처.

        Args:
            session_id: 기존 세션에 저장 (없으면 새 세션 생성)
            zone_id: Zone ID (None이면 Top만)
            all_cameras: 모든 카메라 캡처
            base_path: Node.js에서 지정하는 저장 경로

        Returns:
            {camera_id: image_path} 매핑
        """
        # base_path가 지정되면 새 recorder 초기화 (Node.js 경로 지정 지원)
        if base_path or not self._media_recorder:
            self.init_media_recorder(base_path=base_path)

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

    # =========================================================================
    # 연속 촬영 기능 (문이 열려있는 동안 계속 이미지 저장)
    # =========================================================================

    def start_continuous_capture(
        self,
        session_id: Optional[str] = None,
        camera_ids: Optional[List[int]] = None,
        interval: float = 0.5,
        include_video: bool = True,
        use_base_path_directly: bool = False,
    ) -> Dict[str, Any]:
        """
        연속 촬영 시작.

        문이 열려있는 동안 지정된 간격으로 이미지를 계속 저장합니다.

        Args:
            session_id: 세션 ID (없으면 자동 생성)
            camera_ids: 촬영할 카메라 ID 목록 (기본: [0] = Top 카메라)
            interval: 촬영 간격 (초, 기본: 0.5초)
            include_video: 영상도 함께 녹화할지 여부
            use_base_path_directly: True면 Node.js가 전체 경로를 지정한 경우

        Returns:
            {
                "session_id": str,
                "cameras": List[int],
                "interval": float,
                "paths": Dict[str, str]
            }
        """
        if self._continuous_capture_active:
            logger.warning("Continuous capture already active")
            return {
                "session_id": self._continuous_capture_session_id,
                "already_active": True
            }

        if not self._media_recorder:
            self.init_media_recorder()

        # 카메라 목록 결정 (기본: Top 카메라만)
        if camera_ids is None:
            camera_ids = [TOP_CAMERA_ID]

        # 세션 ID 생성
        if session_id is None:
            from datetime import datetime, timezone, timedelta
            KST = timezone(timedelta(hours=9))
            session_id = datetime.now(KST).strftime("%Y%m%d_%H%M%S")

        self._continuous_capture_session_id = session_id
        self._continuous_capture_interval = interval

        # 세션 생성 (Node.js 경로 사용 시 직접 사용)
        # init_media_recorder에서 이미 base_path 설정됨
        self._media_recorder.create_session(
            camera_ids,
            session_id,
            use_base_path_directly=use_base_path_directly,
        )

        # 영상 녹화도 시작
        if include_video:
            self._media_recorder.start_video_recording(session_id)

        # 연속 촬영 스레드 시작
        self._continuous_capture_stop_event.clear()
        self._continuous_capture_active = True
        self._continuous_capture_thread = threading.Thread(
            target=self._continuous_capture_loop,
            args=(session_id, camera_ids, interval, include_video),
            daemon=True,
            name="ContinuousCapture",
        )
        self._continuous_capture_thread.start()

        paths = self._media_recorder.get_session_paths(session_id)

        logger.info(
            f"Continuous capture started: session={session_id}, "
            f"cameras={camera_ids}, interval={interval}s"
        )

        return {
            "session_id": session_id,
            "cameras": camera_ids,
            "interval": interval,
            "include_video": include_video,
            "paths": paths,
        }

    def _continuous_capture_loop(
        self,
        session_id: str,
        camera_ids: List[int],
        interval: float,
        include_video: bool,
    ) -> None:
        """
        연속 촬영 루프.

        지정된 간격으로 이미지를 캡처하고 저장합니다.
        """
        frame_count = 0

        while not self._continuous_capture_stop_event.is_set():
            try:
                # 각 카메라에서 프레임 캡처 및 저장
                for cam_id in camera_ids:
                    if cam_id in self._cameras:
                        frame = self._cameras[cam_id].get_frame()
                        if frame is not None:
                            # 이미지 저장
                            self._media_recorder.save_image(
                                session_id, cam_id, frame
                            )
                            # 영상에도 프레임 기록
                            if include_video:
                                self._media_recorder.write_video_frame(
                                    session_id, cam_id, frame
                                )

                frame_count += 1

                if frame_count % 10 == 0:
                    logger.debug(
                        f"Continuous capture: {frame_count} frames captured"
                    )

            except Exception as e:
                logger.error(f"Continuous capture error: {e}")

            # 간격 대기 (stop 이벤트로 중단 가능)
            self._continuous_capture_stop_event.wait(interval)

        logger.info(f"Continuous capture loop ended: {frame_count} total frames")

    def stop_continuous_capture(self) -> Optional[Dict[str, Any]]:
        """
        연속 촬영 중지.

        Returns:
            세션 정보 (저장된 파일 경로 등)
        """
        if not self._continuous_capture_active:
            logger.warning("No active continuous capture")
            return None

        # 중지 신호 전송
        self._continuous_capture_stop_event.set()

        # 스레드 종료 대기
        if self._continuous_capture_thread and self._continuous_capture_thread.is_alive():
            self._continuous_capture_thread.join(timeout=2.0)

        self._continuous_capture_active = False

        # 세션 종료 및 결과 반환
        session_id = self._continuous_capture_session_id
        result = None

        if session_id and self._media_recorder:
            result = self._media_recorder.close_session(session_id)

        self._continuous_capture_session_id = None

        logger.info(f"Continuous capture stopped: session={session_id}")

        return result

    @property
    def is_continuous_capture_active(self) -> bool:
        """연속 촬영 활성 여부"""
        return self._continuous_capture_active

    def get_continuous_capture_status(self) -> Dict[str, Any]:
        """연속 촬영 상태 조회"""
        return {
            "active": self._continuous_capture_active,
            "session_id": self._continuous_capture_session_id,
            "interval": self._continuous_capture_interval,
        }

    # =========================================================================
    # Top 카메라 영상 전용 녹화 (데드볼트 열림 ~ 닫힘)
    # =========================================================================

    def start_top_video_only(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Top 카메라 영상만 녹화 시작.

        데드볼트가 열릴 때 호출하여 문이 닫힐 때까지
        Top 카메라의 영상만 녹화합니다 (이미지 저장 없음).

        Args:
            session_id: 세션 ID (없으면 자동 생성)

        Returns:
            {
                "session_id": str,
                "video_path": str
            }
        """
        if not self._media_recorder:
            self.init_media_recorder()

        # 세션 ID 생성
        if session_id is None:
            from datetime import datetime, timezone, timedelta
            KST = timezone(timedelta(hours=9))
            session_id = datetime.now(KST).strftime("%Y%m%d_%H%M%S")

        # Top 카메라만으로 세션 생성
        self._media_recorder.create_session([TOP_CAMERA_ID], session_id)

        # 영상 녹화 시작
        self._media_recorder.start_video_recording(session_id)

        # 연속 영상 프레임 기록 스레드 시작
        self._top_video_session_id = session_id
        self._top_video_stop_event = threading.Event()
        self._top_video_thread = threading.Thread(
            target=self._top_video_recording_loop,
            args=(session_id,),
            daemon=True,
            name="TopVideoRecording",
        )
        self._top_video_thread.start()

        paths = self._media_recorder.get_session_paths(session_id)

        logger.info(f"Top video recording started: session={session_id}")

        return {
            "session_id": session_id,
            "video_path": paths.get("video", {}).get(str(TOP_CAMERA_ID)),
            "paths": paths,
        }

    def _top_video_recording_loop(self, session_id: str) -> None:
        """
        Top 카메라 영상 녹화 루프.

        FPS에 맞춰 프레임을 캡처하고 영상에 기록합니다.
        """
        interval = 1.0 / self.fps
        frame_count = 0

        while not self._top_video_stop_event.is_set():
            try:
                if TOP_CAMERA_ID in self._cameras:
                    frame = self._cameras[TOP_CAMERA_ID].get_frame()
                    if frame is not None:
                        self._media_recorder.write_video_frame(
                            session_id, TOP_CAMERA_ID, frame
                        )
                        frame_count += 1

                        if frame_count % 100 == 0:
                            logger.debug(
                                f"Top video recording: {frame_count} frames"
                            )

            except Exception as e:
                logger.error(f"Top video recording error: {e}")

            self._top_video_stop_event.wait(interval)

        logger.info(f"Top video recording loop ended: {frame_count} total frames")

    def stop_top_video_only(self) -> Optional[Dict[str, Any]]:
        """
        Top 카메라 영상 녹화 중지.

        Returns:
            세션 정보 (저장된 파일 경로 등)
        """
        if not hasattr(self, '_top_video_session_id') or not self._top_video_session_id:
            logger.warning("No active top video recording")
            return None

        # 중지 신호 전송
        if hasattr(self, '_top_video_stop_event'):
            self._top_video_stop_event.set()

        # 스레드 종료 대기
        if hasattr(self, '_top_video_thread') and self._top_video_thread and self._top_video_thread.is_alive():
            self._top_video_thread.join(timeout=2.0)

        # 세션 종료 및 결과 반환
        session_id = self._top_video_session_id
        result = None

        if session_id and self._media_recorder:
            result = self._media_recorder.close_session(session_id)

        self._top_video_session_id = None

        logger.info(f"Top video recording stopped: session={session_id}")

        return result

    @property
    def is_top_video_recording(self) -> bool:
        """Top 영상 녹화 중 여부"""
        return hasattr(self, '_top_video_session_id') and self._top_video_session_id is not None

    # =========================================================================
    # 시간 제한 촬영 (무게 변화 시 3초간 이미지 + 영상)
    # =========================================================================

    def start_timed_capture(
        self,
        session_id: str,
        camera_ids: List[int],
        duration: float = 3.0,
        interval: float = 0.1,
        save_images: bool = True,
        save_side_video: bool = True,
    ) -> Dict[str, Any]:
        """
        시간 제한 촬영 시작.

        무게 변화 시 호출하여 지정된 시간 동안
        이미지와 영상을 저장합니다.

        Args:
            session_id: 세션 ID (기존 세션에 추가)
            camera_ids: 촬영할 카메라 ID 목록 [Top, Side]
            duration: 촬영 시간 (초, 기본: 3초)
            interval: 촬영 간격 (초, 기본: 0.1초 = 10fps)
            save_images: 이미지 저장 여부
            save_side_video: Side 카메라 영상 저장 여부

        Returns:
            {
                "session_id": str,
                "cameras": List[int],
                "duration": float,
                "paths": Dict
            }
        """
        if not self._media_recorder:
            self.init_media_recorder()

        # 세션이 없으면 생성
        if session_id not in self._media_recorder._sessions:
            self._media_recorder.create_session(camera_ids, session_id)

        # Side 카메라 영상 녹화 시작 (Top 제외)
        side_cameras = [cid for cid in camera_ids if cid != TOP_CAMERA_ID]
        if save_side_video and side_cameras:
            self._media_recorder.start_video_recording(session_id, cameras=side_cameras)

        # 시간 제한 촬영 스레드 시작
        capture_thread = threading.Thread(
            target=self._timed_capture_loop,
            args=(session_id, camera_ids, duration, interval, save_images, save_side_video, side_cameras),
            daemon=True,
            name=f"TimedCapture-{session_id}",
        )
        capture_thread.start()

        logger.info(
            f"Timed capture started: session={session_id}, "
            f"cameras={camera_ids}, duration={duration}s"
        )

        return {
            "session_id": session_id,
            "cameras": camera_ids,
            "duration": duration,
            "interval": interval,
            "save_images": save_images,
            "save_side_video": save_side_video,
        }

    def _timed_capture_loop(
        self,
        session_id: str,
        camera_ids: List[int],
        duration: float,
        interval: float,
        save_images: bool,
        save_side_video: bool,
        side_cameras: List[int],
    ) -> None:
        """
        시간 제한 촬영 루프.

        지정된 시간 동안 이미지를 캡처하고 저장합니다.
        """
        start_time = time.time()
        frame_count = 0

        while (time.time() - start_time) < duration:
            try:
                for cam_id in camera_ids:
                    if cam_id in self._cameras:
                        frame = self._cameras[cam_id].get_frame()
                        if frame is not None:
                            # 이미지 저장
                            if save_images:
                                self._media_recorder.save_image(
                                    session_id, cam_id, frame
                                )
                            # Side 영상에 프레임 기록
                            if save_side_video and cam_id in side_cameras:
                                self._media_recorder.write_video_frame(
                                    session_id, cam_id, frame
                                )

                frame_count += 1

            except Exception as e:
                logger.error(f"Timed capture error: {e}")

            time.sleep(interval)

        # Side 영상 녹화 중지
        if save_side_video and side_cameras:
            for cam_id in side_cameras:
                self._media_recorder.stop_video_recording_for_camera(session_id, cam_id)

        logger.info(
            f"Timed capture completed: session={session_id}, "
            f"{frame_count} frames in {duration}s"
        )
