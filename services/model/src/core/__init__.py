"""Core module for Model service."""

from core.config import (
    Settings,
    config,
    load_zone_config,
    get_enabled_zones,
    get_max_zone_id,
    is_zone_enabled,
    get_zone_count,
    get_zone_from_channels,
    get_zone_cameras,
    get_snapshot_folder,
    get_top_camera_path,
    get_side_camera_path,
    generate_session_id,
    ZONE_CONFIG,
    ZONE_CHANNEL_MAP,
    ZONE_CAMERA_MAP,
    TOP_CAMERA_ID,
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
    # Config
    "Settings",
    "config",
    "load_zone_config",
    "get_enabled_zones",
    "get_max_zone_id",
    "is_zone_enabled",
    "get_zone_count",
    "get_zone_from_channels",
    "get_zone_cameras",
    "get_snapshot_folder",
    "get_top_camera_path",
    "get_side_camera_path",
    "generate_session_id",
    "ZONE_CONFIG",
    "ZONE_CHANNEL_MAP",
    "ZONE_CAMERA_MAP",
    "TOP_CAMERA_ID",
    # Logging
    "PerformanceLogger",
    "clear_correlation_id",
    "get_correlation_id",
    "get_logger",
    "log_payload",
    "set_correlation_id",
    "setup_logging",
]
