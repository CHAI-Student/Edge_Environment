from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel


class CameraStatus(BaseModel):
    """Single camera status"""

    camera_id: int
    device_index: Optional[int] = None  # 물리적 디바이스 인덱스
    connected: bool
    running: bool
    active: bool
    is_top_camera: bool
    zone_id: Optional[int]


class AllCamerasStatus(BaseModel):
    """All cameras status"""

    initialized: bool
    streaming: bool
    cameras: List[CameraStatus]


class InitializeResponse(BaseModel):
    """Camera initialization response"""

    success: bool
    status: Dict[int, bool]  # camera_id → connected
    message: str


class FrameResponse(BaseModel):
    """Frame response metadata (actual image is binary)"""

    camera_id: int
    timestamp: float
    width: int
    height: int


class ZoneFramesResponse(BaseModel):
    """Zone frames metadata"""

    zone_id: int
    side_camera_id: int
    top_camera_id: int
    has_side_frame: bool
    has_top_frame: bool


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str
    initialized: bool
    streaming: bool
    connected_cameras: int
