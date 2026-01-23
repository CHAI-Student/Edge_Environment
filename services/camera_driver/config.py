from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, List, Tuple, Optional
import os
import json
import logging
from pathlib import Path

__all__ = ["settings", "ZONE_CAMERA_MAP", "CAMERA_ID_MAPPING", "load_camera_mapping"]

logger = logging.getLogger(__name__)


# Zone to Camera Mapping (기본 정수 인덱스 기반)
# Zone → Side Camera ID
# Top Camera (ID 0) is shared across all zones
ZONE_CAMERA_MAP: Dict[int, int] = {
    0: 1,  # Zone 0 → Camera 1
    1: 2,  # Zone 1 → Camera 2
    2: 3,  # Zone 2 → Camera 3
    3: 4,  # Zone 3 → Camera 4
    4: 5,  # Zone 4 → Camera 5
}

TOP_CAMERA_ID = 0
ZONE_CAMERA_IDS: List[int] = [1, 2, 3, 4, 5]
ALL_CAMERA_IDS: List[int] = [0, 1, 2, 3, 4, 5]


# 카메라 고유 ID 기반 매핑 설정
# identifier: USB 시리얼 또는 고유 ID
# fallback_index: 고유 ID 매칭 실패 시 사용할 인덱스
CAMERA_ID_MAPPING: Dict[str, Dict] = {
    "top": {
        "identifier": "",  # 고유 ID (설정 시 자동 매칭)
        "fallback_index": 0,
        "zone": "top",
    },
    "zone_0": {
        "identifier": "",
        "fallback_index": 1,
        "zone": 0,
    },
    "zone_1": {
        "identifier": "",
        "fallback_index": 2,
        "zone": 1,
    },
    "zone_2": {
        "identifier": "",
        "fallback_index": 3,
        "zone": 2,
    },
    "zone_3": {
        "identifier": "",
        "fallback_index": 4,
        "zone": 3,
    },
    "zone_4": {
        "identifier": "",
        "fallback_index": 5,
        "zone": 4,
    },
}


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
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # FastAPI server settings
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8003)

    # Camera settings
    resolution_width: int = Field(default=640)
    resolution_height: int = Field(default=480)
    fps: int = Field(default=30)
    buffer_size: int = Field(default=60)

    # JPEG quality for streaming
    jpeg_quality: int = Field(default=80)

    # Device scanning settings
    max_scan_index: int = Field(default=10, description="최대 스캔 디바이스 인덱스")

    # Auto-reconnect settings
    auto_reconnect: bool = Field(default=True, description="자동 재연결 활성화")
    reconnect_interval: float = Field(default=5.0, description="재연결 시도 간격 (초)")
    max_reconnect_attempts: int = Field(default=10, description="최대 재연결 시도 횟수")


settings = Settings()

# 시작 시 매핑 설정 로드 시도
load_camera_mapping()
