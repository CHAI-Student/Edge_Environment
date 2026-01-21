from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, List, Tuple

__all__ = ["settings", "ZONE_CAMERA_MAP"]


# Zone to Camera Mapping
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


settings = Settings()
