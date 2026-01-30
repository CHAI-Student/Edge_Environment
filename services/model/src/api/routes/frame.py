"""
Frame API Routes.

POST /api/frame - 이미지 프레임 수신
"""

import time
import logging

from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Depends
from pydantic import BaseModel

import numpy as np

from buffer import FrameBuffer
from api.deps import get_frame_buffer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["frame"])


class FrameResponse(BaseModel):
    """프레임 수신 응답."""

    success: bool
    frame_id: str
    session_id: str
    zone_id: int
    camera_id: int
    buffered_frames: int
    timestamp: float


class BufferStatsResponse(BaseModel):
    """버퍼 통계 응답."""

    session_count: int
    total_frames: int
    ttl_seconds: float
    max_sessions: int
    timestamp: float


@router.post("/frame", response_model=FrameResponse)
async def receive_frame(
    zone_id: int = Form(..., description="Zone ID (0-4)"),
    camera_id: int = Form(..., description="Camera ID (0=top, 1-5=side)"),
    image: UploadFile = File(..., description="Raw image bytes"),
    format: str = Form("bgr", description="Image format (bgr or rgb)"),
    width: int = Form(..., description="Image width"),
    height: int = Form(..., description="Image height"),
    session_id: str = Form(..., description="Session ID"),
    buffer: FrameBuffer = Depends(get_frame_buffer),
):
    """
    이미지 프레임 수신.

    Node.js (또는 Camera Driver)에서 캡처한 이미지를 수신하여
    메모리 버퍼에 저장합니다.

    Args:
        zone_id: Zone ID (0-4)
        camera_id: Camera ID (0=top, 1-5=side)
        image: Raw image bytes (HWC)
        format: 이미지 형식 ("bgr" 또는 "rgb")
        width: 이미지 너비
        height: 이미지 높이
        session_id: 세션 ID
        buffer: FrameBuffer 의존성

    Returns:
        FrameResponse: 수신 결과
    """
    try:
        # 1. Raw bytes 읽기
        raw_bytes = await image.read()

        if len(raw_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty image data")

        # 2. numpy 배열로 변환
        expected_size = height * width * 3  # 3 channels (RGB/BGR)

        if len(raw_bytes) != expected_size:
            # JPEG/PNG 등 압축된 이미지 처리
            import cv2

            nparr = np.frombuffer(raw_bytes, np.uint8)
            img_array = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img_array is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to decode image. Expected raw size: {expected_size}, got: {len(raw_bytes)}",
                )

            # 디코딩된 이미지는 이미 BGR 형식
            format = "bgr"
        else:
            # Raw bytes 직접 변환
            img_array = np.frombuffer(raw_bytes, dtype=np.uint8)
            img_array = img_array.reshape((height, width, 3))

        # 3. 버퍼에 저장
        frame_id = buffer.add_frame(
            session_id=session_id,
            zone_id=zone_id,
            camera_id=camera_id,
            image=img_array,
            format=format,
        )

        # 4. 현재 세션의 프레임 수
        buffered_frames = buffer.get_frame_count(session_id)

        logger.info(
            f"Frame received: session={session_id}, zone={zone_id}, "
            f"camera={camera_id}, frame_id={frame_id}, "
            f"size={img_array.shape}, buffered={buffered_frames}"
        )

        return FrameResponse(
            success=True,
            frame_id=frame_id,
            session_id=session_id,
            zone_id=zone_id,
            camera_id=camera_id,
            buffered_frames=buffered_frames,
            timestamp=time.time(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Frame receive failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/frame/stats", response_model=BufferStatsResponse)
async def get_buffer_stats(
    buffer: FrameBuffer = Depends(get_frame_buffer),
):
    """
    버퍼 통계 조회.

    Returns:
        BufferStatsResponse: 버퍼 통계
    """
    stats = buffer.get_stats()

    return BufferStatsResponse(
        session_count=stats["session_count"],
        total_frames=stats["total_frames"],
        ttl_seconds=stats["ttl_seconds"],
        max_sessions=stats["max_sessions"],
        timestamp=time.time(),
    )


@router.delete("/frame/session/{session_id}")
async def clear_session(
    session_id: str,
    buffer: FrameBuffer = Depends(get_frame_buffer),
):
    """
    세션 정리.

    Args:
        session_id: 세션 ID
        buffer: FrameBuffer 의존성

    Returns:
        삭제 결과
    """
    cleared = buffer.clear_session(session_id)

    return {
        "success": cleared,
        "session_id": session_id,
        "timestamp": time.time(),
    }
