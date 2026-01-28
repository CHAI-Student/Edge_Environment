"""
Model Service Configuration.

Zone-Channel-Camera 매핑 및 서비스 설정.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import os
import json
import logging

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
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
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


@dataclass
class ModelServiceConfig:
    """
    Model 서비스 전체 설정.

    Note (경량화):
        io_board_url, camera_driver_url 제거됨.
        Model 서비스는 더 이상 SSE 구독이나 카메라 직접 호출을 하지 않습니다.
        모든 데이터는 Node.js 오케스트레이터가 수집하여 전달합니다.
    """

    # 서비스 포트
    host: str = "0.0.0.0"
    port: int = 8002

    # 이미지 저장 경로 설정 (Node.js가 저장, Model이 읽음)
    snapshot_base_path: str = field(
        default_factory=lambda: os.getenv("SNAPSHOT_BASE_PATH", "/data/snapshots")
    )
    # 이미지 파일명 패턴
    top_camera_filename: str = "top_cam.jpg"
    side_camera_filename_pattern: str = "zone{zone_id}_cam.jpg"  # zone0_cam.jpg, zone1_cam.jpg, ...

    # Node.js Orchestrator 설정
    nodejs_url: str = field(
        default_factory=lambda: os.getenv("NODEJS_URL", "http://localhost:8889")
    )
    nodejs_judgment_endpoint: str = "/api/sensor/judgment"

    # Vision 설정
    yolo_model_path: str = field(
        default_factory=lambda: os.getenv("YOLO_MODEL_PATH", "models/siyeon_best.pt")
    )
    hand_class_id: int = 0  # 손 클래스 ID
    max_distance_px: float = 150.0  # 손-상품 최대 거리 (픽셀)
    top_k: int = 1  # 추출할 후보 수 (최고 confidence 클래스만)

    # 무게 검증 설정
    tolerance_percent: float = 0.10  # 허용 오차 10%
    min_weight_change: float = 5.0  # 최소 무게 변화량 (g)
    max_combination_size: int = 2  # 최대 조합 크기

    # 앙상블 설정 (동일 가중치)
    top_weight: float = 0.5  # Top 카메라 가중치
    side_weight: float = 0.5  # Side 카메라 가중치
    common_class_bonus: float = 0.2  # 공통 클래스 보너스

    # 로깅
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )


# 글로벌 설정 인스턴스
config = ModelServiceConfig()


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


def generate_session_id() -> str:
    """
    세션 ID 생성 (YYMMDD_HHMMSS 형식).

    Returns:
        세션 ID 문자열
    """
    from datetime import datetime
    return datetime.now().strftime("%y%m%d_%H%M%S")
