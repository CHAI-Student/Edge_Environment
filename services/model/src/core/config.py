"""
Model Service Configuration.

Zone-Channel-Camera 매핑 및 서비스 설정.
Pydantic BaseSettings 기반 환경변수 설정.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Zone 설정 (zone_mapping.json에서 로드)
ZONE_CONFIG: Dict[str, Dict] = {}

# Zone-Channel 매핑 (동적으로 로드됨)
ZONE_CHANNEL_MAP: Dict[int, List[int]] = {}

# Zone-Camera 매핑 (동적으로 로드됨)
ZONE_CAMERA_MAP: Dict[int, int] = {}

# 상단 카메라 ID (공유)
TOP_CAMERA_ID = 0


def load_zone_config(config_path: Optional[str] = None) -> Dict[str, Dict]:
    """
    Zone 매핑 설정 로드.

    zone_mapping.json에서 zone 설정을 로드하고,
    enabled된 zone만 ZONE_CHANNEL_MAP, ZONE_CAMERA_MAP에 등록합니다.

    Args:
        config_path: 설정 파일 경로 (없으면 기본 경로 사용)

    Returns:
        전체 zone 설정
    """
    global ZONE_CONFIG, ZONE_CHANNEL_MAP, ZONE_CAMERA_MAP

    if config_path is None:
        # 기본 경로: project/config/zone_mapping.json
        # src/core/config.py -> services/model -> Edge_Environment
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "config",
            "zone_mapping.json"
        )

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

    # enabled된 zone만 매핑에 등록
    ZONE_CHANNEL_MAP.clear()
    ZONE_CAMERA_MAP.clear()

    for zone_id_str, zone_data in ZONE_CONFIG.items():
        try:
            zone_id = int(zone_id_str)
            if zone_data.get("enabled", True):
                # Channel 매핑
                channels = zone_data.get("loadcell_channels", [zone_id * 2, zone_id * 2 + 1])
                ZONE_CHANNEL_MAP[zone_id] = channels
                # Camera 매핑
                side_camera_id = zone_data.get("side_camera_id", zone_id + 1)
                ZONE_CAMERA_MAP[zone_id] = side_camera_id
        except ValueError:
            continue

    logger.info(f"Model service enabled zones: {list(ZONE_CHANNEL_MAP.keys())}")
    logger.info(f"ZONE_CHANNEL_MAP: {ZONE_CHANNEL_MAP}")
    logger.info(f"ZONE_CAMERA_MAP: {ZONE_CAMERA_MAP}")

    return ZONE_CONFIG


def get_enabled_zones() -> List[int]:
    """활성화된 zone ID 목록 반환."""
    return sorted(ZONE_CHANNEL_MAP.keys())


def get_max_zone_id() -> int:
    """활성화된 zone 중 최대 ID 반환."""
    if not ZONE_CHANNEL_MAP:
        return -1
    return max(ZONE_CHANNEL_MAP.keys())


def is_zone_enabled(zone_id: int) -> bool:
    """특정 zone이 활성화되어 있는지 확인."""
    return zone_id in ZONE_CHANNEL_MAP


def get_zone_count() -> int:
    """활성화된 zone 개수 반환."""
    return len(ZONE_CHANNEL_MAP)


# 모듈 로드 시 zone 설정 로드
load_zone_config()


def get_zone_from_channels(changed_indices: List[int]) -> Optional[int]:
    """
    변화된 채널 인덱스에서 Zone ID 추출.

    Args:
        changed_indices: 변화가 감지된 채널 인덱스 리스트

    Returns:
        Zone ID 또는 None (여러 Zone에 걸쳐있거나 매칭 안 됨)
    """
    detected_zones = set()

    for idx in changed_indices:
        for zone_id, channels in ZONE_CHANNEL_MAP.items():
            if idx in channels:
                detected_zones.add(zone_id)
                break

    if len(detected_zones) == 1:
        return detected_zones.pop()

    return None


def get_zone_cameras(zone_id: int) -> tuple:
    """
    Zone에 대한 Top + Side 카메라 ID 반환.

    Args:
        zone_id: Zone ID (활성화된 zone만 유효)

    Returns:
        (top_camera_id, side_camera_id)
    """
    return (TOP_CAMERA_ID, ZONE_CAMERA_MAP.get(zone_id, 1))


# =============================================================================
# Pydantic Settings Classes
# =============================================================================


class APIModel(BaseModel):
    """API server configuration settings."""

    host: str = Field(
        default="0.0.0.0",
        description="API server host",
    )
    port: int = Field(
        default=8002,
        description="API server port",
    )
    log_level: str = Field(
        default="info",
        description="API log level",
    )
    timeout_graceful_shutdown: int = Field(
        default=10,
        description="Graceful shutdown timeout in seconds",
    )

    @field_validator("port", mode="after")
    def validate_port(cls, value: int) -> int:
        if value <= 0 or value > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {value}")
        return value

    @field_validator("log_level", mode="after")
    def validate_log_level(cls, value: str) -> str:
        valid_levels = [
            "critical",
            "error",
            "warning",
            "info",
            "debug",
            "trace",
        ]
        if value.lower() not in valid_levels:
            raise ValueError(f"Invalid log level: {value}")
        return value.lower()


class VisionModel(BaseModel):
    """Vision configuration settings."""

    yolo_model_path: str = Field(
        default="models/siyeon_best.pt",
        description="YOLO model path (.pt or .engine). Supports relative (project root) or absolute paths. Auto-fallback: .engine → .pt if CUDA unavailable.",
    )
    hand_class_id: int = Field(
        default=0,
        description="Hand class ID in YOLO model",
    )
    max_distance_px: float = Field(
        default=150.0,
        description="Max distance in pixels for hand-product proximity",
    )
    top_k: int = Field(
        default=1,
        description="Top-K candidates to extract",
    )

    # Ensemble settings
    top_weight: float = Field(
        default=0.5,
        description="Top camera weight in ensemble",
    )
    side_weight: float = Field(
        default=0.5,
        description="Side camera weight in ensemble",
    )
    common_class_bonus: float = Field(
        default=0.2,
        description="Bonus for common classes between cameras",
    )

    # Motion Tracking settings
    use_motion_tracking: bool = Field(
        default=True,
        description="Enable motion tracking",
    )
    max_motion_bonus: float = Field(
        default=0.3,
        description="Maximum motion bonus",
    )
    min_motion_correlation: float = Field(
        default=0.5,
        description="Minimum correlation for motion bonus",
    )
    motion_lookback_frames: int = Field(
        default=3,
        description="Frames for motion vector calculation",
    )


class WeightModel(BaseModel):
    """Weight verification configuration settings."""

    tolerance_percent: float = Field(
        default=0.10,
        description="Weight tolerance percentage (0.10 = 10%)",
    )
    min_weight_change: float = Field(
        default=5.0,
        description="Minimum weight change in grams",
    )
    max_combination_size: int = Field(
        default=2,
        description="Maximum combination size for weight matching",
    )


class Settings(BaseSettings):
    """
    Global application settings.

    Environment Variables (with MODEL__ prefix):
        MODEL__API__HOST: API server host (default: 0.0.0.0)
        MODEL__API__PORT: API server port (default: 8002)
        MODEL__API__LOG_LEVEL: Log level (default: info)
        MODEL__VISION__YOLO_MODEL_PATH: YOLO model path
        MODEL__NODEJS_URL: Node.js orchestrator URL
    """

    model_config = SettingsConfigDict(
        env_prefix="MODEL__",
        env_nested_delimiter="__",
    )

    api: APIModel = APIModel()
    vision: VisionModel = VisionModel()
    weight: WeightModel = WeightModel()

    # Snapshot settings
    snapshot_base_path: str = Field(
        default="/data/snapshots",
        description="Base path for snapshot storage",
    )
    top_camera_filename: str = Field(
        default="top_cam.jpg",
        description="Top camera filename",
    )
    side_camera_filename_pattern: str = Field(
        default="zone{zone_id}_cam.jpg",
        description="Side camera filename pattern",
    )

    # Node.js Orchestrator settings
    nodejs_url: str = Field(
        default="http://localhost:8888",
        description="Node.js orchestrator URL",
    )
    nodejs_judgment_endpoint: str = Field(
        default="/api/sensor/judgment",
        description="Node.js judgment endpoint",
    )

    # Legacy compatibility properties
    @property
    def host(self) -> str:
        return self.api.host

    @property
    def port(self) -> int:
        return self.api.port

    @property
    def log_level(self) -> str:
        return self.api.log_level

    @property
    def yolo_model_path(self) -> str:
        return self.vision.yolo_model_path

    @property
    def hand_class_id(self) -> int:
        return self.vision.hand_class_id

    @property
    def max_distance_px(self) -> float:
        return self.vision.max_distance_px

    @property
    def top_k(self) -> int:
        return self.vision.top_k

    @property
    def tolerance_percent(self) -> float:
        return self.weight.tolerance_percent

    @property
    def min_weight_change(self) -> float:
        return self.weight.min_weight_change

    @property
    def max_combination_size(self) -> int:
        return self.weight.max_combination_size

    @property
    def top_weight(self) -> float:
        return self.vision.top_weight

    @property
    def side_weight(self) -> float:
        return self.vision.side_weight

    @property
    def common_class_bonus(self) -> float:
        return self.vision.common_class_bonus

    @property
    def use_motion_tracking(self) -> bool:
        return self.vision.use_motion_tracking

    @property
    def max_motion_bonus(self) -> float:
        return self.vision.max_motion_bonus

    @property
    def min_motion_correlation(self) -> float:
        return self.vision.min_motion_correlation

    @property
    def motion_lookback_frames(self) -> int:
        return self.vision.motion_lookback_frames


# Global config instance (for backward compatibility)
config = Settings()


def get_snapshot_folder(session_id: str) -> str:
    """
    스냅샷 폴더 경로 생성.

    Args:
        session_id: 세션 ID (예: "260121_143025")

    Returns:
        폴더 경로 (예: "/data/snapshots/260121_143025/")
    """
    return os.path.join(config.snapshot_base_path, session_id)


def get_top_camera_path(session_id: str) -> str:
    """
    Top 카메라 이미지 경로.

    Args:
        session_id: 세션 ID

    Returns:
        이미지 파일 경로
    """
    return os.path.join(
        get_snapshot_folder(session_id),
        config.top_camera_filename
    )


def get_side_camera_path(session_id: str, zone_id: int) -> str:
    """
    Side 카메라 이미지 경로.

    Args:
        session_id: 세션 ID
        zone_id: Zone ID (활성화된 zone만 유효)

    Returns:
        이미지 파일 경로
    """
    filename = config.side_camera_filename_pattern.format(zone_id=zone_id)
    return os.path.join(
        get_snapshot_folder(session_id),
        filename
    )


def get_kst_now():
    """
    한국 표준시(KST, UTC+9) 현재 시각 반환.

    Returns:
        KST timezone-aware datetime 객체
    """
    from datetime import datetime, timezone, timedelta

    KST = timezone(timedelta(hours=9))
    return datetime.now(KST)


def generate_session_id() -> str:
    """
    세션 ID 생성 (YYMMDD_HHMMSS 형식, KST 기준).

    Returns:
        세션 ID 문자열
    """
    return get_kst_now().strftime("%y%m%d_%H%M%S")


if __name__ == "__main__":
    settings = Settings()
    print(settings.model_dump_json(indent=4))
