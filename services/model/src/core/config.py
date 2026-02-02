"""
Model Service Configuration.

Pydantic BaseSettings 기반 환경변수 설정.
Jetson Orin Nano TensorRT 전용.
"""

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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
    """Vision configuration settings (Jetson Orin Nano TensorRT only)."""

    yolo_model_path: str = Field(
        default="models/siyeon_best.engine",
        description="YOLO TensorRT engine path (.engine only). Jetson Orin Nano required.",
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


class WeightModel(BaseModel):
    """Weight verification configuration settings."""

    tolerance_percent: float = Field(
        default=0.10,
        description="Weight tolerance percentage (0.10 = 10%), 레거시 용도",
    )
    tolerance_grams: float = Field(
        default=5.0,
        description="Fixed weight tolerance in grams (고정 허용 오차)",
    )
    min_weight_change: float = Field(
        default=5.0,
        description="Minimum weight change in grams",
    )
    max_combination_size: int = Field(
        default=2,
        description="Maximum combination size for weight matching",
    )


class BufferModel(BaseModel):
    """Session store configuration settings (v4.2)."""

    ttl_seconds: float = Field(
        default=300.0,
        description="Session TTL in seconds (default: 5 minutes)",
    )
    max_sessions: int = Field(
        default=100,
        description="Maximum concurrent sessions",
    )
    cleanup_interval_seconds: float = Field(
        default=60.0,
        description="Background cleanup interval in seconds (v4.2)",
    )


class DoorSessionModel(BaseModel):
    """Door Session configuration settings (v4.2)."""

    enabled: bool = Field(
        default=True,
        description="Door Session 기능 활성화 여부",
    )
    yaml_dir: str = Field(
        default="data/sessions",
        description="YAML 저장 디렉토리",
    )
    session_timeout_seconds: float = Field(
        default=30.0,
        description="마지막 trigger 후 타임아웃 (초)",
    )
    weight_tolerance_grams: float = Field(
        default=3.0,
        description="반환 매칭 무게 허용 오차 (g)",
    )
    max_duration_seconds: float = Field(
        default=600.0,
        description="최대 세션 지속 시간 (초, 10분)",
    )
    yaml_retention_days: int = Field(
        default=7,
        description="완료된 YAML 세션 파일 보관 기간 (일, v4.2)",
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
    buffer: BufferModel = BufferModel()
    door_session: DoorSessionModel = DoorSessionModel()

    # Node.js Orchestrator settings
    nodejs_url: str = Field(
        default="http://localhost:8888",
        description="Node.js orchestrator URL",
    )
    nodejs_judgment_endpoint: str = Field(
        default="/api/sensor/judgment",
        description="Node.js judgment endpoint",
    )

    # Convenience properties for commonly used settings
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
    def top_weight(self) -> float:
        return self.vision.top_weight

    @property
    def side_weight(self) -> float:
        return self.vision.side_weight

    @property
    def common_class_bonus(self) -> float:
        return self.vision.common_class_bonus


# Global config instance
config = Settings()


def get_kst_now():
    """
    한국 표준시(KST, UTC+9) 현재 시각 반환.

    Returns:
        KST timezone-aware datetime 객체
    """
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
