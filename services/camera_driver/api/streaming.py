"""
Camera Driver SSE Streaming

MJPEG 스트리밍
"""

import asyncio
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..config import settings, ALL_CAMERA_IDS, is_zone_enabled, get_enabled_zones
from .routes import get_manager

router = APIRouter()


async def generate_mjpeg_stream(camera_id: int) -> AsyncGenerator[bytes, None]:
    """Generate MJPEG stream for a camera"""
    try:
        import cv2
    except ImportError:
        return

    manager = get_manager()
    frame_interval = 1.0 / settings.fps

    while True:
        frame = manager.get_frame(camera_id)
        if frame is not None:
            _, buffer = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality]
            )
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
        await asyncio.sleep(frame_interval)


@router.get("/stream/{camera_id}")
async def stream_camera(camera_id: int):
    """MJPEG stream for a camera"""
    if camera_id not in ALL_CAMERA_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"camera_id must be one of {ALL_CAMERA_IDS}"
        )

    return StreamingResponse(
        generate_mjpeg_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


async def generate_zone_mjpeg_stream(zone_id: int) -> AsyncGenerator[bytes, None]:
    """Generate MJPEG stream for zone (side camera only)"""
    try:
        import cv2
    except ImportError:
        return

    from ..config import ZONE_CAMERA_MAP

    camera_id = ZONE_CAMERA_MAP.get(zone_id)
    if camera_id is None:
        return

    manager = get_manager()
    frame_interval = 1.0 / settings.fps

    while True:
        frame = manager.get_frame(camera_id)
        if frame is not None:
            _, buffer = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality]
            )
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
        await asyncio.sleep(frame_interval)


@router.get("/stream/zone/{zone_id}")
async def stream_zone(zone_id: int):
    """MJPEG stream for zone side camera"""
    if not is_zone_enabled(zone_id):
        enabled = get_enabled_zones()
        raise HTTPException(
            status_code=400,
            detail=f"zone_id {zone_id} is not enabled. Enabled zones: {enabled}"
        )

    return StreamingResponse(
        generate_zone_mjpeg_stream(zone_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
