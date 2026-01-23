"""
Camera Device Scanner

카메라 디바이스 동적 스캔 및 고유 ID 기반 매핑.

지원 플랫폼:
- Windows: DirectShow 백엔드, WMI 쿼리
- Linux: V4L2, /dev/v4l/by-id/ 심볼릭 링크

사용 예시:
    scanner = DeviceScanner()
    devices = scanner.scan_all_devices()
    index = scanner.find_by_identifier("USB_Camera_12345678")
"""

import os
import sys
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None

logger = logging.getLogger(__name__)


@dataclass
class CameraDeviceInfo:
    """카메라 디바이스 정보."""

    device_index: int
    backend: str = ""
    name: str = ""
    identifier: str = ""  # 고유 식별자 (USB serial 등)
    usb_path: str = ""    # USB 경로 (Linux: /dev/v4l/by-id/...)
    width: int = 0
    height: int = 0
    fps: float = 0.0
    is_available: bool = False
    extra_info: Dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"Camera[{self.device_index}]: {self.name or 'Unknown'} ({self.identifier})"


class DeviceScanner:
    """
    카메라 디바이스 스캐너.

    시스템에 연결된 카메라를 스캔하고 고유 ID를 수집합니다.
    """

    def __init__(self, max_index: int = 10):
        """
        초기화.

        Args:
            max_index: 스캔할 최대 디바이스 인덱스
        """
        self.max_index = max_index
        self._cached_devices: List[CameraDeviceInfo] = []
        self._identifier_to_index: Dict[str, int] = {}
        self._is_windows = sys.platform == "win32"
        self._is_linux = sys.platform.startswith("linux")

    def scan_all_devices(self, refresh: bool = False) -> List[CameraDeviceInfo]:
        """
        모든 카메라 디바이스 스캔.

        Args:
            refresh: 캐시 무시하고 재스캔

        Returns:
            CameraDeviceInfo 리스트
        """
        if self._cached_devices and not refresh:
            return self._cached_devices

        devices = []
        self._identifier_to_index.clear()

        if not CV2_AVAILABLE:
            logger.warning("OpenCV not available, cannot scan cameras")
            return devices

        # 디바이스 인덱스 스캔
        for idx in range(self.max_index):
            device = self._probe_device(idx)
            if device and device.is_available:
                devices.append(device)
                if device.identifier:
                    self._identifier_to_index[device.identifier] = idx

        # Linux: /dev/v4l/by-id/ 스캔으로 보강
        if self._is_linux:
            self._scan_linux_v4l_by_id(devices)

        self._cached_devices = devices
        logger.info(f"Scanned {len(devices)} camera devices")

        return devices

    def _probe_device(self, device_index: int) -> Optional[CameraDeviceInfo]:
        """
        단일 디바이스 정보 수집.

        Args:
            device_index: 디바이스 인덱스

        Returns:
            CameraDeviceInfo 또는 None
        """
        if not CV2_AVAILABLE:
            return None

        try:
            # 빠른 연결 테스트
            cap = cv2.VideoCapture(device_index)
            if not cap.isOpened():
                cap.release()
                return None

            # 디바이스 정보 수집
            backend = cap.getBackendName() if hasattr(cap, 'getBackendName') else "Unknown"
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            # 프레임 테스트
            ret, _ = cap.read()
            is_available = ret

            cap.release()

            device = CameraDeviceInfo(
                device_index=device_index,
                backend=backend,
                width=width,
                height=height,
                fps=fps,
                is_available=is_available,
            )

            # 플랫폼별 추가 정보 수집
            if self._is_windows:
                self._get_windows_device_info(device)
            elif self._is_linux:
                self._get_linux_device_info(device)

            logger.debug(f"Probed device {device_index}: {device}")
            return device

        except Exception as e:
            logger.debug(f"Failed to probe device {device_index}: {e}")
            return None

    def _get_windows_device_info(self, device: CameraDeviceInfo) -> None:
        """
        Windows에서 추가 디바이스 정보 수집.

        DirectShow 속성 또는 WMI 사용.
        """
        try:
            # WMI를 통한 USB 카메라 정보 수집 시도
            import subprocess

            # WMIC로 USB 비디오 디바이스 조회
            result = subprocess.run(
                ["wmic", "path", "Win32_PnPEntity", "where",
                 "Caption like '%Camera%' or Caption like '%Webcam%' or Caption like '%USB Video%'",
                 "get", "Caption,DeviceID", "/format:csv"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines[1:]:  # 헤더 스킵
                    parts = line.strip().split(",")
                    if len(parts) >= 3:
                        caption = parts[1]
                        device_id = parts[2]

                        # 디바이스 인덱스와 매칭 시도 (순서 기반)
                        if device_id:
                            # USB VID/PID 추출
                            vid_match = re.search(r"VID_([0-9A-Fa-f]+)", device_id)
                            pid_match = re.search(r"PID_([0-9A-Fa-f]+)", device_id)

                            if vid_match and pid_match:
                                device.identifier = f"USB_{vid_match.group(1)}_{pid_match.group(1)}"
                                device.name = caption
                                device.extra_info["device_id"] = device_id
                                break

        except Exception as e:
            logger.debug(f"WMI device info failed: {e}")

        # 식별자가 없으면 기본값 생성
        if not device.identifier:
            device.identifier = f"WIN_CAM_{device.device_index}"
            device.name = f"Camera {device.device_index}"

    def _get_linux_device_info(self, device: CameraDeviceInfo) -> None:
        """
        Linux에서 추가 디바이스 정보 수집.

        /dev/v4l/by-id/ 심볼릭 링크 및 V4L2 정보 사용.
        """
        try:
            import subprocess

            # udevadm으로 디바이스 정보 수집
            video_path = f"/dev/video{device.device_index}"
            result = subprocess.run(
                ["udevadm", "info", "--query=all", "--name", video_path],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                output = result.stdout

                # ID_SERIAL 추출
                serial_match = re.search(r"ID_SERIAL=(.+)", output)
                if serial_match:
                    device.identifier = serial_match.group(1).strip()

                # ID_MODEL 추출
                model_match = re.search(r"ID_MODEL=(.+)", output)
                if model_match:
                    device.name = model_match.group(1).strip()

                # ID_PATH 추출
                path_match = re.search(r"ID_PATH=(.+)", output)
                if path_match:
                    device.usb_path = path_match.group(1).strip()

        except Exception as e:
            logger.debug(f"udevadm info failed: {e}")

        # /dev/v4l/by-id/ 에서 매칭 시도
        self._match_v4l_by_id(device)

        # 식별자가 없으면 기본값 생성
        if not device.identifier:
            device.identifier = f"LINUX_CAM_{device.device_index}"
            device.name = f"Camera {device.device_index}"

    def _match_v4l_by_id(self, device: CameraDeviceInfo) -> None:
        """
        /dev/v4l/by-id/ 심볼릭 링크와 매칭.
        """
        v4l_by_id = Path("/dev/v4l/by-id")
        if not v4l_by_id.exists():
            return

        try:
            video_path = f"/dev/video{device.device_index}"

            for link in v4l_by_id.iterdir():
                if link.is_symlink():
                    target = link.resolve()
                    if str(target) == video_path:
                        # 심볼릭 링크 이름에서 식별자 추출
                        device.usb_path = str(link)
                        if not device.identifier:
                            device.identifier = link.name
                        logger.debug(f"Matched {video_path} to {link}")
                        break

        except Exception as e:
            logger.debug(f"v4l/by-id matching failed: {e}")

    def _scan_linux_v4l_by_id(self, devices: List[CameraDeviceInfo]) -> None:
        """
        Linux /dev/v4l/by-id/ 디렉토리 스캔.

        기존 디바이스 정보 보강.
        """
        v4l_by_id = Path("/dev/v4l/by-id")
        if not v4l_by_id.exists():
            return

        try:
            for link in v4l_by_id.iterdir():
                if link.is_symlink() and "-video-index" in link.name:
                    target = link.resolve()
                    target_name = target.name  # video0, video1, ...

                    if target_name.startswith("video"):
                        try:
                            idx = int(target_name[5:])

                            # 기존 디바이스와 매칭
                            for device in devices:
                                if device.device_index == idx:
                                    device.usb_path = str(link)
                                    if not device.identifier or device.identifier.startswith("LINUX_CAM_"):
                                        device.identifier = link.name
                                    self._identifier_to_index[device.identifier] = idx
                                    break

                        except ValueError:
                            pass

        except Exception as e:
            logger.debug(f"v4l/by-id scan failed: {e}")

    def find_by_identifier(self, identifier: str) -> Optional[int]:
        """
        고유 식별자로 디바이스 인덱스 찾기.

        Args:
            identifier: 고유 식별자

        Returns:
            디바이스 인덱스 또는 None
        """
        # 캐시 확인
        if identifier in self._identifier_to_index:
            return self._identifier_to_index[identifier]

        # 캐시가 비어있으면 스캔
        if not self._cached_devices:
            self.scan_all_devices()
            if identifier in self._identifier_to_index:
                return self._identifier_to_index[identifier]

        # 부분 매칭 시도
        for device in self._cached_devices:
            if identifier in device.identifier or device.identifier in identifier:
                return device.device_index

        return None

    def rebuild_mapping(self, config_mapping: Dict) -> Dict[str, int]:
        """
        설정 기반 Zone-카메라 매핑 재구성.

        USB 포트 변경 등으로 인덱스가 변경된 경우 매핑을 갱신합니다.

        Args:
            config_mapping: 설정 파일의 매핑 정보
                {
                    "zone_id": {
                        "identifier": "USB_Camera_SERIAL",
                        "fallback_index": 1,
                    }
                }

        Returns:
            {zone_id: device_index} 매핑
        """
        # 최신 디바이스 정보로 갱신
        self.scan_all_devices(refresh=True)

        zone_to_index: Dict[str, int] = {}

        for zone_key, zone_config in config_mapping.items():
            zone_id = zone_key
            identifier = zone_config.get("identifier")
            fallback = zone_config.get("fallback_index")

            # 고유 ID로 찾기
            if identifier:
                idx = self.find_by_identifier(identifier)
                if idx is not None:
                    zone_to_index[zone_id] = idx
                    logger.info(f"Zone {zone_id}: Mapped to device {idx} by identifier '{identifier}'")
                    continue

            # 폴백 인덱스 사용
            if fallback is not None:
                # 폴백 인덱스가 사용 가능한지 확인
                for device in self._cached_devices:
                    if device.device_index == fallback and device.is_available:
                        zone_to_index[zone_id] = fallback
                        logger.warning(
                            f"Zone {zone_id}: Using fallback index {fallback} "
                            f"(identifier '{identifier}' not found)"
                        )
                        break
                else:
                    logger.error(f"Zone {zone_id}: Fallback index {fallback} not available")

        return zone_to_index

    def get_device_by_index(self, index: int) -> Optional[CameraDeviceInfo]:
        """
        인덱스로 디바이스 정보 조회.

        Args:
            index: 디바이스 인덱스

        Returns:
            CameraDeviceInfo 또는 None
        """
        for device in self._cached_devices:
            if device.device_index == index:
                return device
        return None

    def get_available_indices(self) -> List[int]:
        """
        사용 가능한 디바이스 인덱스 리스트.

        Returns:
            디바이스 인덱스 리스트
        """
        if not self._cached_devices:
            self.scan_all_devices()

        return [d.device_index for d in self._cached_devices if d.is_available]

    def print_devices(self) -> None:
        """디바이스 목록 출력 (디버깅용)."""
        devices = self.scan_all_devices()

        print("\n=== Camera Devices ===")
        for device in devices:
            print(f"  [{device.device_index}] {device.name}")
            print(f"      Identifier: {device.identifier}")
            print(f"      Backend: {device.backend}")
            print(f"      Resolution: {device.width}x{device.height} @ {device.fps:.1f}fps")
            if device.usb_path:
                print(f"      USB Path: {device.usb_path}")
            print(f"      Available: {device.is_available}")
        print()
