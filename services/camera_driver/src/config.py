"""
Re-export config from core.config for backward compatibility.

All modules using `from ..config import ...` will work with this re-export.
"""

from core.config import (
    # Settings
    Settings,
    settings,
    # Zone functions and constants
    load_zone_config,
    get_enabled_zones,
    get_max_zone_id,
    is_zone_enabled,
    ZONE_CONFIG,
    ZONE_CAMERA_MAP,
    TOP_CAMERA_ID,
    ZONE_CAMERA_IDS,
    ALL_CAMERA_IDS,
    # Camera mapping
    CAMERA_ID_MAPPING,
    load_camera_mapping,
    save_camera_mapping,
    update_camera_identifier,
    # Device mapping
    DEVICE_PHYSICAL_MAP,
    load_device_map,
    get_physical_device_index,
    # Time utilities
    get_kst_now,
    generate_session_id,
)

__all__ = [
    "Settings",
    "settings",
    "load_zone_config",
    "get_enabled_zones",
    "get_max_zone_id",
    "is_zone_enabled",
    "ZONE_CONFIG",
    "ZONE_CAMERA_MAP",
    "TOP_CAMERA_ID",
    "ZONE_CAMERA_IDS",
    "ALL_CAMERA_IDS",
    "CAMERA_ID_MAPPING",
    "load_camera_mapping",
    "save_camera_mapping",
    "update_camera_identifier",
    "DEVICE_PHYSICAL_MAP",
    "load_device_map",
    "get_physical_device_index",
    "get_kst_now",
    "generate_session_id",
]
