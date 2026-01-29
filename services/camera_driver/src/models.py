"""
Camera Driver Pydantic Models
"""

from typing import Dict, List, Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """General health response."""
    status: str = "ok"


class CameraHealthResponse(BaseModel):
    """Camera health response with storage status."""
    cameras: str  # "HEALTHY" or "UNHEALTHY"
    storage: str  # "HEALTHY" or "UNHEALTHY"


class CameraStatus(BaseModel):
    """Individual camera status."""
    camera_id: int
    device_index: Optional[int] = None
    connected: bool
    running: bool
    active: bool
    is_top_camera: bool
    zone_id: Optional[int] = None


class AllCamerasStatus(BaseModel):
    """All cameras status response."""
    initialized: bool
    streaming: bool
    cameras: List[CameraStatus]


class InitializeResponse(BaseModel):
    """Camera initialization response."""
    success: bool
    status: Dict[int, bool]  # camera_id -> initialized
    message: str


class ZoneFramesResponse(BaseModel):
    """Zone frames metadata response."""
    zone_id: int
    side_camera_id: int
    top_camera_id: int
    has_side_frame: bool
    has_top_frame: bool
