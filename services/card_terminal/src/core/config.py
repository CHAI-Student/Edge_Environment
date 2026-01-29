"""
Configuration management for Card Terminal module.

This module provides enterprise-grade configuration management using environment
variables with validation and type safety via Pydantic BaseSettings.

Environment Variables (with CARD_TERMINAL__ prefix):
    CARD_TERMINAL__API__HOST: API server bind address (default: 0.0.0.0)
    CARD_TERMINAL__API__PORT: API server port (default: 5000)
    CARD_TERMINAL__API__LOG_LEVEL: Logging level (default: info)
    CARD_TERMINAL__CAT__HOST: CAT device server bind address (default: 0.0.0.0)
    CARD_TERMINAL__CAT__PORT: CAT device server port (default: 5001)
    CARD_TERMINAL__COMM_TIMEOUT: Device communication timeout (default: 30.0)
    CARD_TERMINAL__SHUTDOWN_TIMEOUT: Graceful shutdown timeout (default: 10.0)
    CARD_TERMINAL__LOG_FORMAT: Log format - 'json' or 'text' (default: text)

Usage:
    from core.config import Settings

    settings = Settings()
    print(f"API Port: {settings.api.port}")
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class APIModel(BaseModel):
    """API server configuration settings."""

    host: str = Field(
        default="0.0.0.0",
        description="API server host",
    )
    port: int = Field(
        default=8001,
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

    @field_validator("timeout_graceful_shutdown", mode="after")
    def validate_timeout_graceful_shutdown(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"Timeout for graceful shutdown must be positive, got {value}")
        return value


class CATModel(BaseModel):
    """CAT device server configuration settings."""

    host: str = Field(
        default="0.0.0.0",
        description="CAT server host",
    )
    port: int = Field(
        default=5001,
        description="CAT server port",
    )

    @field_validator("port", mode="after")
    def validate_port(cls, value: int) -> int:
        if value <= 0 or value > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {value}")
        return value


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_prefix="CARD_TERMINAL__",
        env_nested_delimiter="__",
    )

    api: APIModel = APIModel()
    cat: CATModel = CATModel()

    comm_timeout: float = Field(
        default=30.0,
        description="Device communication timeout in seconds",
    )
    shutdown_timeout: float = Field(
        default=10.0,
        description="Graceful shutdown timeout in seconds",
    )
    log_format: Literal["json", "text"] = Field(
        default="text",
        description="Log format: 'json' or 'text'",
    )

    @field_validator("comm_timeout", "shutdown_timeout", mode="after")
    def validate_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"Timeout must be positive, got {value}")
        return value

    def configure_logging(self) -> None:
        """
        Configure Python logging based on settings.

        Sets up logging format (text or JSON) and level from configuration.
        Call this once at application startup.
        """
        log_level = getattr(logging, self.api.log_level.upper())

        if self.log_format == "json":
            # JSON structured logging for production
            logging.basicConfig(
                level=log_level,
                format='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        else:
            # Human-readable text format for development
            logging.basicConfig(
                level=log_level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        # Reduce verbosity of third-party libraries
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("aiosqlite").setLevel(logging.WARNING)


if __name__ == "__main__":
    settings = Settings()
    print(settings.model_dump_json(indent=4))
