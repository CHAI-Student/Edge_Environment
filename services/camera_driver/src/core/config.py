from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, List, Tuple, Optional
import os
import json
import logging
from pathlib import Path

__all__ = [
    "settings",
    "ZONE_CAMERA_MAP",
    "CAMERA_ID_MAPPING",
    "load_camera_mapping",
    "get_physical_device_index",
    "load_device_map",
    "DEVICE_PHYSICAL_MAP",
    "load_zone_config",
    "get_enabled_zones",
    "get_max_zone_id",
    "is_zone_enabled",
    "ZONE_CONFIG",
]

logger = logging.getLogger(__name__)


# Zone 설정 (zone_mapping.json에서 로드)
ZONE_CONFIG: Dict[str, Dict] = {}

# Zone to Camera Mapping (동적으로 로드됨)
# Zone → Side Camera ID
# Top Camera (ID 0) is shared across all zones
ZONE_CAMERA_MAP: Dict[int, int] = {}

TOP_CAMERA_ID = 0
ZONE_CAMERA_IDS: List[int] = []
ALL_CAMERA_IDS: List[int] = []


def load_zone_config(config_path: Optional[str] = None) -> Dict[str, Dict]:
    """
    Zone 매핑 설정 로드.

    zone_mapping.json에서 zone 설정을 로드하고,
    enabled된 zone만 ZONE_CAMERA_MAP에 등록합니다.

    Args:
        config_path: 설정 파일 경로 (없으면 기본 경로 사용)

    Returns:
        전체 zone 설정
    """
    global ZONE_CONFIG, ZONE_CAMERA_MAP, ZONE_CAMERA_IDS, ALL_CAMERA_IDS

    if config_path is None:
        # 기본 경로: project/config/zone_mapping.json
        # src/core/config.py (5 levels up) -> Edge_Environment
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        print(project_root)
        config_path = os.path.join(project_root, "config", "zone_mapping.json")

    # 기본값 (fallback) - 5개 zone 전부 활성화
    default_zones = {
        "0": {"loadcell_channels": [0, 1], "side_camera_id": 1, "enabled": True},
        "1": {"loadcell_channels": [2, 3], "side_camera_id": 2, "enabled": True},
        "2": {"loadcell_channels": [4, 5], "side_camera_id": 3, "enabled": True},
        "3": {"loadcell_channels": [6, 7], "side_camera_id": 4, "enabled": True},
        "4": {"loadcell_channels": [8, 9], "side_camera_id": 5, "enabled": True},
    }

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "zones" in data:
                ZONE_CONFIG = data["zones"]
            else:
                ZONE_CONFIG = default_zones

            logger.info(f"Zone config loaded from {config_path}")

        except Exception as e:
            logger.warning(f"Failed to load zone config: {e}, using defaults")
            ZONE_CONFIG = default_zones
    else:
        logger.info(f"Zone config not found at {config_path}, using defaults")
        ZONE_CONFIG = default_zones

    # 환경변수로 zone 개수 override 가능
    # ENABLED_ZONE_COUNT=3 이면 zone 0, 1, 2만 활성화
    env_zone_count = os.environ.get("ENABLED_ZONE_COUNT")
    if env_zone_count:
        try:
            max_zones = int(env_zone_count)
            for zone_id_str, zone_data in ZONE_CONFIG.items():
                try:
                    zone_id = int(zone_id_str)
                    zone_data["enabled"] = zone_id < max_zones
                except ValueError:
                    pass
            logger.info(f"ENABLED_ZONE_COUNT={max_zones}: overriding zone enabled states")
        except ValueError:
            logger.warning(f"Invalid ENABLED_ZONE_COUNT value: {env_zone_count}")

    # enabled된 zone만 ZONE_CAMERA_MAP에 등록
    ZONE_CAMERA_MAP.clear()
    ZONE_CAMERA_IDS.clear()

    for zone_id_str, zone_data in ZONE_CONFIG.items():
        try:
            zone_id = int(zone_id_str)
            if zone_data.get("enabled", True):
                side_camera_id = zone_data.get("side_camera_id", zone_id + 1)
                ZONE_CAMERA_MAP[zone_id] = side_camera_id
                ZONE_CAMERA_IDS.append(side_camera_id)
        except ValueError:
            continue

    # 정렬
    ZONE_CAMERA_IDS.sort()

    # ALL_CAMERA_IDS 업데이트 (Top + enabled zones)
    ALL_CAMERA_IDS.clear()
    ALL_CAMERA_IDS.append(TOP_CAMERA_ID)
    ALL_CAMERA_IDS.extend(ZONE_CAMERA_IDS)

    logger.info(f"Enabled zones: {list(ZONE_CAMERA_MAP.keys())}")
    logger.info(f"ZONE_CAMERA_MAP: {ZONE_CAMERA_MAP}")
    logger.info(f"ALL_CAMERA_IDS: {ALL_CAMERA_IDS}")

    return ZONE_CONFIG


def get_enabled_zones() -> List[int]:
    """활성화된 zone ID 목록 반환."""
    return sorted(ZONE_CAMERA_MAP.keys())


def get_max_zone_id() -> int:
    """활성화된 zone 중 최대 ID 반환."""
    if not ZONE_CAMERA_MAP:
        return -1
    return max(ZONE_CAMERA_MAP.keys())


def is_zone_enabled(zone_id: int) -> bool:
    """특정 zone이 활성화되어 있는지 확인."""
    return zone_id in ZONE_CAMERA_MAP


# 카메라 고유 ID 기반 매핑 설정 (동적으로 빌드됨)
# identifier: USB 시리얼 또는 고유 ID
# fallback_index: 고유 ID 매칭 실패 시 사용할 인덱스
CAMERA_ID_MAPPING: Dict[str, Dict] = {}


def _build_camera_id_mapping() -> Dict[str, Dict]:
    """
    활성화된 zone 기반으로 CAMERA_ID_MAPPING 빌드.
    """
    global CAMERA_ID_MAPPING

    CAMERA_ID_MAPPING = {
        "top": {
            "identifier": "",
            "fallback_index": 0,
            "zone": "top",
        },
    }

    for zone_id, camera_id in ZONE_CAMERA_MAP.items():
        CAMERA_ID_MAPPING[f"zone_{zone_id}"] = {
            "identifier": "",
            "fallback_index": camera_id,
            "zone": zone_id,
        }

    return CAMERA_ID_MAPPING


def load_camera_mapping(config_path: Optional[str] = None) -> Dict[str, Dict]:
    """
    카메라 매핑 설정 로드.

    JSON 파일에서 카메라 고유 ID 매핑을 로드합니다.

    Args:
        config_path: 설정 파일 경로 (없으면 기본 경로 사용)

    Returns:
        카메라 매핑 설정
    """
    global CAMERA_ID_MAPPING

    if config_path is None:
        # 기본 경로: {service_dir}/camera_mapping.json
        config_path = os.path.join(
            os.path.dirname(__file__),
            "camera_mapping.json"
        )

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # cameras 키가 있으면 사용
            if "cameras" in data:
                CAMERA_ID_MAPPING = data["cameras"]
            else:
                CAMERA_ID_MAPPING = data

            logger.info(f"Camera mapping loaded from {config_path}")

        except Exception as e:
            logger.warning(f"Failed to load camera mapping: {e}")

    return CAMERA_ID_MAPPING


def save_camera_mapping(config_path: Optional[str] = None) -> bool:
    """
    카메라 매핑 설정 저장.

    Args:
        config_path: 설정 파일 경로

    Returns:
        저장 성공 여부
    """
    global CAMERA_ID_MAPPING

    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(__file__),
            "camera_mapping.json"
        )

    try:
        data = {
            "version": "1.0",
            "cameras": CAMERA_ID_MAPPING,
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Camera mapping saved to {config_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to save camera mapping: {e}")
        return False


def update_camera_identifier(zone_key: str, identifier: str) -> bool:
    """
    특정 Zone의 카메라 고유 ID 업데이트.

    Args:
        zone_key: Zone 키 (top, zone_0, zone_1, ...)
        identifier: 새 고유 ID

    Returns:
        업데이트 성공 여부
    """
    global CAMERA_ID_MAPPING

    if zone_key in CAMERA_ID_MAPPING:
        CAMERA_ID_MAPPING[zone_key]["identifier"] = identifier
        logger.info(f"Camera identifier updated: {zone_key} -> {identifier}")
        return True

    logger.warning(f"Unknown zone key: {zone_key}")
    return False


class Settings(BaseSettings):
    """
    Camera Driver Service Settings.

    Environment Variables (with CAMERA__ prefix):
        CAMERA__API_HOST: API server host (default: 0.0.0.0)
        CAMERA__API_PORT: API server port (default: 8003)
        CAMERA__NVIDIA_MODE: Use Nvidia device indexing (default: true)
        CAMERA__IO_BOARD_URL: IO Board service URL
        CAMERA__NODEJS_CALLBACK_URL: Node.js callback URL
    """

    model_config = SettingsConfigDict(
        env_prefix="CAMERA__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # FastAPI server settings
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8003)

    # Camera settings
    resolution_width: int = Field(default=640)
    resolution_height: int = Field(default=480)
    fps: int = Field(default=30)
    buffer_size: int = Field(default=90, description="버퍼 크기 (3초 @ 30fps)")

    # JPEG quality for streaming
    jpeg_quality: int = Field(default=80)

    # Image save settings (cropping)
    save_width: int = Field(default=480, description="저장 이미지 너비 (640에서 오른쪽 160px 크롭)")
    save_height: int = Field(default=480, description="저장 이미지 높이")
    crop_from_left: bool = Field(default=True, description="True: 왼쪽 기준 크롭, False: 중앙 크롭")

    # Device scanning settings
    max_scan_index: int = Field(default=12, description="최대 스캔 디바이스 인덱스 (Nvidia 모드 시 12까지)")

    # Auto-reconnect settings
    auto_reconnect: bool = Field(default=True, description="자동 재연결 활성화")
    reconnect_interval: float = Field(default=5.0, description="재연결 시도 간격 (초)")
    max_reconnect_attempts: int = Field(default=10, description="최대 재연결 시도 횟수")

    # Nvidia mode settings (Jetson Orin Nano: video0, video2, video4...)
    nvidia_mode: bool = Field(default=True, description="Nvidia 장치 인덱싱 모드 (짝수 인덱스: 0,2,4,6,8,10)")
    device_map_path: str = Field(default="", description="카메라 디바이스 매핑 설정 파일 경로")

    # IO Board SSE 구독 설정 (Event-Driven Architecture)
    io_board_url: str = Field(default="http://localhost:8000", description="IO Board 서비스 URL")
    nodejs_callback_url: str = Field(default="http://localhost:8889", description="Node.js 오케스트레이터 콜백 URL")

    # 이벤트 기반 녹화 설정
    pre_buffer_seconds: float = Field(default=0.5, description="이벤트 발생 전 버퍼 시간 (초)")
    post_buffer_seconds: float = Field(default=2.5, description="이벤트 발생 후 녹화 시간 (초)")
    save_images: bool = Field(default=True, description="스냅샷 이미지 저장 여부")
    save_videos: bool = Field(default=True, description="영상 파일 저장 여부")

    # 미디어 저장 경로
    media_base_path: str = Field(default="data/", description="미디어 저장 기본 경로 (Edge_Environment/data/)")


settings = Settings()

# 디바이스 매핑 설정 (외부 설정 파일에서 로드)
DEVICE_PHYSICAL_MAP: Dict[int, int] = {}


def load_device_map(config_path: Optional[str] = None) -> Dict[int, int]:
    """
    카메라 디바이스 물리적 인덱스 매핑 로드.

    Args:
        config_path: 설정 파일 경로 (없으면 기본 경로 사용)

    Returns:
        논리적 ID -> 물리적 인덱스 매핑
    """
    global DEVICE_PHYSICAL_MAP, settings

    if config_path is None:
        # 기본 경로: project/config/camera_device_map.json
        # src/core/config.py (5 levels up) -> Edge_Environment
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        config_path = settings.device_map_path or os.path.join(
            project_root, "config", "camera_device_map.json"
        )

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # nvidia_mode 설정 업데이트
            if "nvidia_mode" in data:
                settings.nvidia_mode = data["nvidia_mode"]

            # device_map 로드 (기존 dict를 업데이트하여 참조 유지)
            if "device_map" in data:
                DEVICE_PHYSICAL_MAP.clear()
                DEVICE_PHYSICAL_MAP.update({
                    int(k): v.get("physical_index", int(k))
                    for k, v in data["device_map"].items()
                })

            logger.info(f"Device map loaded from {config_path}: nvidia_mode={settings.nvidia_mode}")
            logger.info(f"DEVICE_PHYSICAL_MAP: {DEVICE_PHYSICAL_MAP}")

        except Exception as e:
            logger.warning(f"Failed to load device map: {e}")

    return DEVICE_PHYSICAL_MAP


def get_physical_device_index(logical_id: int) -> int:
    """
    논리적 카메라 ID를 물리적 디바이스 인덱스로 변환.

    Nvidia Jetson에서는 카메라가 짝수 인덱스(0, 2, 4, 6, 8, 10)로 할당됩니다.

    Args:
        logical_id: 논리적 카메라 ID (0-5)

    Returns:
        물리적 디바이스 인덱스
    """
    # 명시적 매핑이 있으면 사용
    if logical_id in DEVICE_PHYSICAL_MAP:
        return DEVICE_PHYSICAL_MAP[logical_id]

    # Nvidia 모드: 짝수 인덱스 사용
    if settings.nvidia_mode:
        return logical_id * 2

    # 기본: 동일한 인덱스 사용
    return logical_id


# 시작 시 설정 로드 순서:
# 1. Zone 설정 로드 (enabled zone 결정)
# 2. 카메라 ID 매핑 빌드
# 3. 카메라 매핑 로드
# 4. 디바이스 맵 로드
load_zone_config()
_build_camera_id_mapping()
load_camera_mapping()
load_device_map()
