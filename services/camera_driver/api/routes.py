"""
Camera Driver API Routes
"""

import io
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..config import settings, ZONE_CAMERA_MAP, TOP_CAMERA_ID, get_physical_device_index
from ..core import CameraManager
from ..models import (
    AllCamerasStatus,
    CameraHealthResponse,
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
                device_index=c.get("device_index"),
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


def _test_storage_writable() -> bool:
    """저장 경로 쓰기 가능 여부 테스트."""
    try:
        # 프로젝트 루트 기준: Edge_Environment/{날짜시간}/images/cam_0~cam_5
        # camera_driver/api/routes.py 기준 상위 4단계가 프로젝트 루트
        project_root = Path(__file__).parent.parent.parent.parent
        test_session = datetime.now().strftime("%Y%m%d_%H%M%S_healthcheck")
        test_path = project_root / test_session / "images"

        # 6개 카메라 폴더 생성 테스트
        for cam_id in range(6):
            cam_folder = test_path / f"cam_{cam_id}"
            cam_folder.mkdir(parents=True, exist_ok=True)

            # 쓰기 테스트
            test_file = cam_folder / ".write_test"
            test_file.write_text("test")
            test_file.unlink()

        # 정리
        shutil.rmtree(project_root / test_session)
        return True
    except Exception:
        return False


@router.get("/health")
async def health_check() -> CameraHealthResponse:
    """Health check endpoint (IO Board 형식 호환)."""
    manager = get_manager()

    # 1. 카메라 상태 확인 (기존 health_check() 메서드 활용)
    camera_health = manager.health_check()  # {camera_id: bool}

    # 6대 전부 연결 + 프레임 캡처 가능해야 HEALTHY
    all_cameras_ok = (
        len(camera_health) == 6 and
        all(camera_health.values())
    )

    # 2. 저장 경로 쓰기 테스트
    storage_ok = _test_storage_writable()

    return CameraHealthResponse(
        cameras="HEALTHY" if all_cameras_ok else "UNHEALTHY",
        storage="HEALTHY" if storage_ok else "UNHEALTHY",
    )


@router.get("/status/detailed")
async def get_detailed_status() -> dict:
    """Get detailed camera status including device info"""
    manager = get_manager()
    return manager.get_detailed_status()


@router.get("/devices/scan")
async def scan_devices() -> dict:
    """Scan for available camera devices"""
    manager = get_manager()
    devices = manager.scan_devices()
    return {
        "devices": [
            {
                "index": d.device_index,
                "name": d.name,
                "identifier": d.identifier,
                "available": d.is_available,
            }
            for d in devices
        ],
        "nvidia_mode": settings.nvidia_mode,
    }


@router.get("/camera/{camera_id}/frame")
async def get_camera_frame_base64(camera_id: int) -> dict:
    """Get single frame as base64 encoded JPEG"""
    import base64

    if camera_id < 0 or camera_id > 5:
        raise HTTPException(status_code=400, detail="camera_id must be 0-5")

    manager = get_manager()
    frame, timestamp = manager.get_frame_with_timestamp(camera_id)

    if frame is None:
        raise HTTPException(status_code=404, detail=f"No frame from camera {camera_id}")

    # Encode to JPEG and then base64
    try:
        import cv2

        _, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality]
        )
        frame_base64 = base64.b64encode(buffer).decode("utf-8")
        return {
            "camera_id": camera_id,
            "frame": frame_base64,
            "timestamp": timestamp,
            "format": "jpeg",
        }
    except ImportError:
        raise HTTPException(status_code=500, detail="OpenCV not available")


@router.get("/zone/{zone_id}/capture")
async def capture_zone(zone_id: int, include_top: bool = True) -> dict:
    """Capture zone frames as base64"""
    import base64

    if zone_id < 0 or zone_id > 4:
        raise HTTPException(status_code=400, detail="zone_id must be 0-4")

    manager = get_manager()
    side_frame, top_frame = manager.get_zone_frames(zone_id, include_top=include_top)

    result = {
        "zone_id": zone_id,
        "side_camera_id": ZONE_CAMERA_MAP.get(zone_id),
        "zone_frame": None,
        "top_frame": None,
        "timestamp": time.time(),
    }

    try:
        import cv2

        if side_frame is not None:
            _, buffer = cv2.imencode(
                ".jpg", side_frame, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality]
            )
            result["zone_frame"] = base64.b64encode(buffer).decode("utf-8")

        if include_top and top_frame is not None:
            _, buffer = cv2.imencode(
                ".jpg", top_frame, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality]
            )
            result["top_frame"] = base64.b64encode(buffer).decode("utf-8")

    except ImportError:
        raise HTTPException(status_code=500, detail="OpenCV not available")

    return result


from pydantic import BaseModel


class ZoneSnapshotRequest(BaseModel):
    """Zone 스냅샷 요청."""
    session_id: str
    include_top: bool = True


@router.post("/zone/{zone_id}/snapshot")
async def capture_zone_snapshot(zone_id: int, request: ZoneSnapshotRequest) -> dict:
    """
    Zone 스냅샷 캡처 및 파일 저장.

    Node.js 오케스트레이터가 무게 변화 이벤트 시 호출하여
    이미지를 디스크에 저장하고 파일 경로를 반환합니다.

    Args:
        zone_id: Zone ID (0-4)
        request: 요청 본문 (session_id, include_top)

    Returns:
        {
            "session_path": "/data/snapshots/260126143025",
            "images": {
                "cam_0": "/data/snapshots/260126143025/cam_0/snapshot.jpg",
                "cam_1": "/data/snapshots/260126143025/cam_1/snapshot.jpg"
            }
        }
    """
    if zone_id < 0 or zone_id > 4:
        raise HTTPException(status_code=400, detail="zone_id must be 0-4")

    manager = get_manager()

    # 스냅샷 캡처 (기존 메서드 활용)
    saved_paths = manager.capture_snapshot(
        session_id=request.session_id,
        zone_id=zone_id,
        all_cameras=False,
    )

    # 세션 경로 계산
    # 기본 경로: Edge_Environment/{session_id}/images/cam_X
    project_root = Path(__file__).parent.parent.parent.parent
    session_path = str(project_root / request.session_id / "images")

    # 응답 형식 (Node.js 클라이언트 호환)
    images = {}
    for cam_id, path in saved_paths.items():
        images[f"cam_{cam_id}"] = path

    return {
        "success": True,
        "zone_id": zone_id,
        "session_id": request.session_id,
        "session_path": session_path,
        "images": images,
        "timestamp": time.time(),
    }


# =========================================================================
# 녹화 API 엔드포인트
# =========================================================================


@router.post("/recording/start")
async def start_recording(
    zone_id: Optional[int] = None,
    include_top: bool = True,
    record_video: bool = True,
    base_path: Optional[str] = None,
) -> dict:
    """
    녹화 시작.

    Args:
        zone_id: Zone ID (0-4, None이면 전체)
        include_top: Top 카메라 포함 여부
        record_video: 영상 녹화 여부
        base_path: 저장 기본 경로

    Returns:
        세션 ID 및 경로 정보
    """
    manager = get_manager()

    if base_path:
        manager.init_media_recorder(base_path=base_path)
    elif not manager._media_recorder:
        manager.init_media_recorder()

    session_id = manager.start_recording(
        zone_id=zone_id,
        include_top=include_top,
        record_video=record_video,
    )

    if not session_id:
        raise HTTPException(status_code=500, detail="Failed to start recording")

    paths = manager.get_recording_paths(session_id)

    return {
        "success": True,
        "session_id": session_id,
        "zone_id": zone_id,
        "record_video": record_video,
        "paths": paths,
    }


@router.post("/recording/stop")
async def stop_recording() -> dict:
    """
    녹화 중지.

    Returns:
        세션 정보 (저장된 파일 경로 등)
    """
    manager = get_manager()

    if not manager.is_recording:
        raise HTTPException(status_code=400, detail="No active recording")

    result = manager.stop_recording()

    if not result:
        raise HTTPException(status_code=500, detail="Failed to stop recording")

    return {
        "success": True,
        "session_info": result,
    }


@router.post("/recording/snapshot")
async def capture_snapshot(
    zone_id: Optional[int] = None,
    all_cameras: bool = False,
    session_id: Optional[str] = None,
) -> dict:
    """
    스냅샷 캡처.

    Args:
        zone_id: Zone ID (0-4)
        all_cameras: 모든 카메라 캡처
        session_id: 기존 세션에 저장 (없으면 새 세션)

    Returns:
        저장된 이미지 경로 정보
    """
    manager = get_manager()

    if zone_id is not None and (zone_id < 0 or zone_id > 4):
        raise HTTPException(status_code=400, detail="zone_id must be 0-4")

    saved_paths = manager.capture_snapshot(
        session_id=session_id,
        zone_id=zone_id,
        all_cameras=all_cameras,
    )

    return {
        "success": True,
        "saved_count": len(saved_paths),
        "images": {f"cam_{k}": v for k, v in saved_paths.items()},
    }


@router.get("/recording/status")
async def get_recording_status() -> dict:
    """녹화 상태 조회."""
    manager = get_manager()

    return {
        "is_recording": manager.is_recording,
        "has_media_recorder": manager._media_recorder is not None,
    }


@router.post("/recording/session/{session_id}/close")
async def close_session(session_id: str) -> dict:
    """
    녹화 세션 종료.

    Args:
        session_id: 세션 ID

    Returns:
        세션 정보
    """
    manager = get_manager()

    result = manager.close_recording_session(session_id)

    if not result:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return {
        "success": True,
        "session_info": result,
    }
