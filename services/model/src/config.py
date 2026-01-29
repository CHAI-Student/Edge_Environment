"""
Re-export config from core.config for backward compatibility.

All modules using `from ..config import ...` will work with this re-export.
"""

from core.config import (
    # Settings classes
    Settings,
    APIModel,
    VisionModel,
    WeightModel,
    config,
    # Zone functions and constants
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
    # Zone data
    ZONE_CONFIG,
    ZONE_CHANNEL_MAP,
    ZONE_CAMERA_MAP,
    TOP_CAMERA_ID,
)

__all__ = [
    "Settings",
    "APIModel",
    "VisionModel",
    "WeightModel",
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
]
