from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["settings"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    mqtt_broker_host: str = Field(default="localhost")
    mqtt_broker_port: int = Field(default=1883)

    mqtt_client_username: str | None = None
    mqtt_client_password: str | None = None

    division_idx: str = Field(default="DIV001")
    device_idx: str = Field(default="DEV001")

    # FastAPI server settings
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8006)


settings = Settings()
