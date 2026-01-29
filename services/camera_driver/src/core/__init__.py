"""Core module for Camera Driver service."""

from .camera import ZoneCamera, CameraConfig
from .manager import CameraManager
from .device_scanner import DeviceScanner, CameraDeviceInfo
from .media_recorder import MediaRecorder, EventRecorder, RecordingConfig
from .sse_subscriber import IOBoardSSESubscriber, WeightChangeEvent
from .event_recording_manager import EventRecordingManager, MediaPaths
from .config import (
    Settings,
    settings,
    ZONE_CAMERA_MAP,
    CAMERA_ID_MAPPING,
    load_camera_mapping,
    get_physical_device_index,
    load_device_map,
    DEVICE_PHYSICAL_MAP,
    load_zone_config,
    get_enabled_zones,
    get_max_zone_id,
    is_zone_enabled,
    ZONE_CONFIG,
    TOP_CAMERA_ID,
    ZONE_CAMERA_IDS,
    ALL_CAMERA_IDS,
)
from .logging_config import (
    PerformanceLogger,
    clear_correlation_id,
    get_correlation_id,
    get_logger,
    log_payload,
    set_correlation_id,
    setup_logging,
)

__all__ = [
    # Camera components
    "ZoneCamera",
    "CameraConfig",
    "CameraManager",
    "DeviceScanner",
    "CameraDeviceInfo",
    "MediaRecorder",
    "EventRecorder",
    "RecordingConfig",
    "IOBoardSSESubscriber",
    "WeightChangeEvent",
    "EventRecordingManager",
    "MediaPaths",
    # Config
    "Settings",
    "settings",
    "ZONE_CAMERA_MAP",
    "CAMERA_ID_MAPPING",
    "load_camera_mapping",
    "get_physical_device_index",
    "load_device_map",
    "DEVICE_PHYSICAL_MAP",
    "load_zone_config",
    "get_enabled_zones",
    "get_max_zone_id",
    "is_zone_enabled",
    "ZONE_CONFIG",
    "TOP_CAMERA_ID",
    "ZONE_CAMERA_IDS",
    "ALL_CAMERA_IDS",
    # Logging
    "PerformanceLogger",
    "clear_correlation_id",
    "get_correlation_id",
    "get_logger",
    "log_payload",
    "set_correlation_id",
    "setup_logging",
]
