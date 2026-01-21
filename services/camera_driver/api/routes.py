"""
Camera Driver API Routes
"""

import io
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..config import settings, ZONE_CAMERA_MAP, TOP_CAMERA_ID
from ..core import CameraManager
from ..models import (
    AllCamerasStatus,
    CameraStatus,
    HealthResponse,
    InitializeResponse,
    ZoneFramesResponse,
)

router = APIRouter()

# Global camera manager
_manager: CameraManager | None = None


def get_manager() -> CameraManager:
    """Get or create camera manager instance"""
    global _manager
    if _manager is None:
        _manager = CameraManager()
    return _manager


@router.post("/init")
async def initialize() -> InitializeResponse:
    """Initialize all cameras and start streaming"""
    manager = get_manager()
    status = manager.initialize_all()
    manager.start_streaming()
    return InitializeResponse(
        success=any(status.values()),
        status=status,
        message=f"Initialized {sum(status.values())}/{len(status)} cameras",
    )


@router.post("/release")
async def release() -> dict:
    """Release all cameras"""
    manager = get_manager()
    manager.release_all()
    return {"success": True, "message": "All cameras released"}


@router.get("/status")
async def get_status() -> AllCamerasStatus:
    """Get all cameras status"""
    manager = get_manager()
    status = manager.get_status()
    return AllCamerasStatus(
        initialized=status["initialized"],
        streaming=status["streaming"],
        cameras=[
            CameraStatus(
                camera_id=c["camera_id"],
                connected=c["connected"],
                running=c["running"],
                active=c["active"],
                is_top_camera=c["is_top_camera"],
                zone_id=c["zone_id"],
            )
            for c in status["cameras"]
        ],
    )


@router.get("/frame/{camera_id}")
async def get_frame(camera_id: int) -> Response:
    """Get single frame as JPEG"""
    if camera_id < 0 or camera_id > 5:
        raise HTTPException(status_code=400, detail="camera_id must be 0-5")

    manager = get_manager()
    frame = manager.get_frame(camera_id)

    if frame is None:
        raise HTTPException(status_code=404, detail=f"No frame from camera {camera_id}")

    # Encode to JPEG
    try:
        import cv2

        _, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality]
        )
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={
                "X-Camera-ID": str(camera_id),
                "X-Timestamp": str(time.time()),
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="OpenCV not available")


@router.get("/frame/zone/{zone_id}")
async def get_zone_frames(zone_id: int) -> ZoneFramesResponse:
    """Get zone frame metadata (use /frame/{camera_id} for actual frames)"""
    if zone_id < 0 or zone_id > 4:
        raise HTTPException(status_code=400, detail="zone_id must be 0-4")

    manager = get_manager()
    side_frame, top_frame = manager.get_zone_frames(zone_id)

    side_camera_id = ZONE_CAMERA_MAP.get(zone_id, -1)

    return ZoneFramesResponse(
        zone_id=zone_id,
        side_camera_id=side_camera_id,
        top_camera_id=TOP_CAMERA_ID,
        has_side_frame=side_frame is not None,
        has_top_frame=top_frame is not None,
    )


@router.post("/zone/{zone_id}/activate")
async def activate_zone(zone_id: int) -> dict:
    """Activate zone camera (start buffering)"""
    if zone_id < 0 or zone_id > 4:
        raise HTTPException(status_code=400, detail="zone_id must be 0-4")

    manager = get_manager()
    manager.activate_zone_camera(zone_id)
    return {"success": True, "message": f"Zone {zone_id} camera activated"}


@router.post("/zone/{zone_id}/deactivate")
async def deactivate_zone(zone_id: int) -> dict:
    """Deactivate zone camera (stop buffering)"""
    if zone_id < 0 or zone_id > 4:
        raise HTTPException(status_code=400, detail="zone_id must be 0-4")

    manager = get_manager()
    manager.deactivate_zone_camera(zone_id)
    return {"success": True, "message": f"Zone {zone_id} camera deactivated"}


@router.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint"""
    manager = get_manager()
    return HealthResponse(
        status="healthy",
        service="camera_driver",
        initialized=manager.is_initialized,
        streaming=manager.is_streaming,
        connected_cameras=manager.connected_count,
    )
