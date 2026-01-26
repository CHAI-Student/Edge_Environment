"""
Model Service Configuration.

Zone-Channel-Camera 매핑 및 서비스 설정.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import os


# Zone-Channel 매핑 (채널 인덱스는 0-based, io_board SSE 응답 기준)
ZONE_CHANNEL_MAP: Dict[int, List[int]] = {
    0: [0, 1],   # Zone 0: 로드셀 인덱스 0, 1
    1: [2, 3],   # Zone 1: 로드셀 인덱스 2, 3
    2: [4, 5],   # Zone 2: 로드셀 인덱스 4, 5
    3: [6, 7],   # Zone 3: 로드셀 인덱스 6, 7
    4: [8, 9],   # Zone 4: 로드셀 인덱스 8, 9
}

# Zone-Camera 매핑
ZONE_CAMERA_MAP: Dict[int, int] = {
    0: 1,  # Zone 0 → Side Camera 1
    1: 2,  # Zone 1 → Side Camera 2
    2: 3,  # Zone 2 → Side Camera 3
    3: 4,  # Zone 3 → Side Camera 4
    4: 5,  # Zone 4 → Side Camera 5
}

# 상단 카메라 ID (공유)
TOP_CAMERA_ID = 0


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
        zone_id: Zone ID (0-4)

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
        default_factory=lambda: os.getenv("YOLO_MODEL_PATH", "models/yolov8n-products.pt")
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
        zone_id: Zone ID (0-4)

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
