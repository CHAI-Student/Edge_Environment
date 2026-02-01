"""Core module for Model service."""

from core.exceptions import (
    FFmpegError,
    InvalidLoadcellValueError,
    LoadcellDataError,
    ModelServiceError,
    SessionError,
    SessionExpiredError,
    SessionNotFoundError,
    VideoCorruptedError,
    VideoFileNotFoundError,
    VideoProcessingError,
    YOLOGPUError,
    YOLOInferenceError,
    YOLOModelNotLoadedError,
)
from core.config import (
    Settings,
    config,
    generate_session_id,
)
from core.logging_config import (
    PerformanceLogger,
    clear_correlation_id,
    get_correlation_id,
    get_logger,
    log_payload,
    set_correlation_id,
    setup_logging,
)

__all__ = [
    # Exceptions
    "ModelServiceError",
    "VideoProcessingError",
    "VideoFileNotFoundError",
    "VideoCorruptedError",
    "FFmpegError",
    "YOLOInferenceError",
    "YOLOModelNotLoadedError",
    "YOLOGPUError",
    "SessionError",
    "SessionNotFoundError",
    "SessionExpiredError",
    "LoadcellDataError",
    "InvalidLoadcellValueError",
    # Config
    "Settings",
    "config",
    "generate_session_id",
    # Logging
    "PerformanceLogger",
    "clear_correlation_id",
    "get_correlation_id",
    "get_logger",
    "log_payload",
    "set_correlation_id",
    "setup_logging",
]
