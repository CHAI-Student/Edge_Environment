"""
MQTT Client Service Configuration.

Environment Variables (with MQTT__ prefix):
    MQTT__API_HOST: API server host (default: 0.0.0.0)
    MQTT__API_PORT: API server port (default: 8006)
    MQTT__MQTT_BROKER_HOST: MQTT broker host (default: localhost)
    MQTT__MQTT_BROKER_PORT: MQTT broker port (default: 1883)
    MQTT__DIVISION_IDX: Division identifier (default: DIV001)
    MQTT__DEVICE_IDX: Device identifier (default: DEV001)
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["settings", "Settings"]


class Settings(BaseSettings):
    """MQTT Client Service Settings."""

    model_config = SettingsConfigDict(
        env_prefix="MQTT__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MQTT Broker settings
    mqtt_broker_host: str = Field(default="localhost", description="MQTT broker host")
    mqtt_broker_port: int = Field(default=1883, description="MQTT broker port")

    # MQTT Client credentials
    mqtt_client_username: str | None = Field(default=None, description="MQTT client username")
    mqtt_client_password: str | None = Field(default=None, description="MQTT client password")

    # Device identifiers
    division_idx: str = Field(default="DIV001", description="Division identifier")
    device_idx: str = Field(default="DEV001", description="Device identifier")

    # FastAPI server settings
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8006, description="API server port")
    log_level: str = Field(default="INFO", description="Log level")


settings = Settings()
