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

from ..config import (
    settings,
    ZONE_CAMERA_MAP,
    TOP_CAMERA_ID,
    ALL_CAMERA_IDS,
    get_physical_device_index,
    get_enabled_zones,
    get_max_zone_id,
    is_zone_enabled,
)
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
    if camera_id not in ALL_CAMERA_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"camera_id must be one of {ALL_CAMERA_IDS}"
        )

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
    if not is_zone_enabled(zone_id):
        enabled = get_enabled_zones()
        raise HTTPException(
            status_code=400,
            detail=f"zone_id {zone_id} is not enabled. Enabled zones: {enabled}"
        )

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
    if not is_zone_enabled(zone_id):
        enabled = get_enabled_zones()
        raise HTTPException(
            status_code=400,
            detail=f"zone_id {zone_id} is not enabled. Enabled zones: {enabled}"
        )

    manager = get_manager()
    manager.activate_zone_camera(zone_id)
    return {"success": True, "message": f"Zone {zone_id} camera activated"}


@router.post("/zone/{zone_id}/deactivate")
async def deactivate_zone(zone_id: int) -> dict:
    """Deactivate zone camera (stop buffering)"""
    if not is_zone_enabled(zone_id):
        enabled = get_enabled_zones()
        raise HTTPException(
            status_code=400,
            detail=f"zone_id {zone_id} is not enabled. Enabled zones: {enabled}"
        )

    manager = get_manager()
    manager.deactivate_zone_camera(zone_id)
    return {"success": True, "message": f"Zone {zone_id} camera deactivated"}


def _test_storage_writable() -> bool:
    """저장 경로 쓰기 가능 여부 테스트."""
    try:
        # 프로젝트 루트 기준: Edge_Environment/{날짜시간}/images/cam0~cam5
        # camera_driver/api/routes.py 기준 상위 4단계가 프로젝트 루트
        project_root = Path(__file__).parent.parent.parent.parent
        test_session = datetime.now().strftime("%Y%m%d_%H%M%S_healthcheck")
        test_path = project_root / test_session / "images"

        # 활성화된 카메라 폴더 생성 테스트
        for cam_id in ALL_CAMERA_IDS:
            cam_folder = test_path / f"cam{cam_id}"
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

    # 활성화된 카메라 전부 연결 + 프레임 캡처 가능해야 HEALTHY
    expected_camera_count = len(ALL_CAMERA_IDS)
    all_cameras_ok = (
        len(camera_health) == expected_camera_count and
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


@router.get("/zones/config")
async def get_zone_config() -> dict:
    """
    현재 Zone 설정 조회.

    활성화된 zone 목록과 카메라 매핑 정보를 반환합니다.
    ENABLED_ZONE_COUNT 환경변수로 zone 개수를 조절할 수 있습니다.

    Returns:
        Zone 설정 정보
    """
    from ..config import ZONE_CONFIG

    return {
        "enabled_zones": get_enabled_zones(),
        "max_zone_id": get_max_zone_id(),
        "zone_camera_map": dict(ZONE_CAMERA_MAP),
        "all_camera_ids": list(ALL_CAMERA_IDS),
        "zone_config": dict(ZONE_CONFIG),
        "top_camera_id": TOP_CAMERA_ID,
    }


@router.get("/camera/{camera_id}/frame")
async def get_camera_frame_base64(camera_id: int) -> dict:
    """Get single frame as base64 encoded JPEG"""
    import base64

    if camera_id not in ALL_CAMERA_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"camera_id must be one of {ALL_CAMERA_IDS}"
        )

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

    if not is_zone_enabled(zone_id):
        enabled = get_enabled_zones()
        raise HTTPException(
            status_code=400,
            detail=f"zone_id {zone_id} is not enabled. Enabled zones: {enabled}"
        )

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
        zone_id: Zone ID (활성화된 zone만 허용)
        request: 요청 본문 (session_id, include_top)

    Returns:
        {
            "session_path": "/data/snapshots/260126143025",
            "images": {
                "cam0": "data/260126143025/images/cam0/snapshot.jpg",
                "cam1": "data/260126143025/images/cam1/snapshot.jpg"
            }
        }
    """
    if not is_zone_enabled(zone_id):
        enabled = get_enabled_zones()
        raise HTTPException(
            status_code=400,
            detail=f"zone_id {zone_id} is not enabled. Enabled zones: {enabled}"
        )

    manager = get_manager()

    # 스냅샷 캡처 (기존 메서드 활용)
    saved_paths = manager.capture_snapshot(
        session_id=request.session_id,
        zone_id=zone_id,
        all_cameras=False,
    )

    # 세션 경로 계산
    # 기본 경로: Edge_Environment/data/{session_id}/images/camX
    # settings.media_base_path 사용 (기본값: "data/")
    base_path = Path(settings.media_base_path) if settings.media_base_path else Path("data/")
    session_path = str(base_path / request.session_id / "images")

    # 응답 형식 (Node.js 클라이언트 호환)
    images = {}
    for cam_id, path in saved_paths.items():
        images[f"cam{cam_id}"] = path

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
        zone_id: Zone ID (활성화된 zone만 허용)
        all_cameras: 모든 카메라 캡처
        session_id: 기존 세션에 저장 (없으면 새 세션)

    Returns:
        저장된 이미지 경로 정보
    """
    manager = get_manager()

    if zone_id is not None and not is_zone_enabled(zone_id):
        enabled = get_enabled_zones()
        raise HTTPException(
            status_code=400,
            detail=f"zone_id {zone_id} is not enabled. Enabled zones: {enabled}"
        )

    saved_paths = manager.capture_snapshot(
        session_id=session_id,
        zone_id=zone_id,
        all_cameras=all_cameras,
    )

    return {
        "success": True,
        "saved_count": len(saved_paths),
        "images": {f"cam{k}": v for k, v in saved_paths.items()},
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


# =========================================================================
# SSE 구독 및 이벤트 녹화 API
# =========================================================================

# Global SSE subscriber and event recording manager
_sse_subscriber = None
_event_recording_manager = None


def get_sse_subscriber():
    """Get SSE subscriber instance"""
    global _sse_subscriber
    return _sse_subscriber


def get_event_recording_manager():
    """Get event recording manager instance"""
    global _event_recording_manager
    return _event_recording_manager


def init_sse_components(sse_subscriber, event_recording_manager):
    """Initialize SSE components (called from main.py)"""
    global _sse_subscriber, _event_recording_manager
    _sse_subscriber = sse_subscriber
    _event_recording_manager = event_recording_manager


class CallbackRegisterRequest(BaseModel):
    """콜백 등록 요청."""
    url: str


@router.post("/callback/register")
async def register_callback(request: CallbackRegisterRequest) -> dict:
    """
    Node.js 콜백 URL 등록.

    Camera Driver가 미디어 저장 완료 시 이 URL로 알림을 보냅니다.

    Args:
        request: 콜백 URL

    Returns:
        등록 결과
    """
    event_manager = get_event_recording_manager()

    if event_manager is None:
        raise HTTPException(status_code=503, detail="Event recording manager not initialized")

    # 콜백 URL 업데이트
    event_manager._nodejs_callback_url = request.url

    return {
        "success": True,
        "message": f"Callback URL registered: {request.url}",
        "timestamp": time.time(),
    }


@router.get("/sse/status")
async def get_sse_status() -> dict:
    """
    SSE 연결 상태 조회.

    Returns:
        SSE 구독 상태 및 이벤트 녹화 상태
    """
    sse_sub = get_sse_subscriber()
    event_manager = get_event_recording_manager()

    sse_status = sse_sub.get_status() if sse_sub else {"running": False, "connected": False}
    recording_status = event_manager.get_status() if event_manager else {}

    return {
        "sse_subscriber": sse_status,
        "event_recording": recording_status,
        "timestamp": time.time(),
    }


@router.post("/sse/start")
async def start_sse_subscription() -> dict:
    """
    SSE 구독 시작.

    IO Board SSE 스트림 구독을 수동으로 시작합니다.

    Returns:
        시작 결과
    """
    sse_sub = get_sse_subscriber()

    if sse_sub is None:
        raise HTTPException(status_code=503, detail="SSE subscriber not initialized")

    if sse_sub._running:
        return {
            "success": True,
            "message": "SSE subscriber already running",
            "status": sse_sub.get_status(),
        }

    await sse_sub.start()

    return {
        "success": True,
        "message": "SSE subscriber started",
        "status": sse_sub.get_status(),
    }


@router.post("/sse/stop")
async def stop_sse_subscription() -> dict:
    """
    SSE 구독 중지.

    IO Board SSE 스트림 구독을 수동으로 중지합니다.

    Returns:
        중지 결과
    """
    sse_sub = get_sse_subscriber()

    if sse_sub is None:
        raise HTTPException(status_code=503, detail="SSE subscriber not initialized")

    await sse_sub.stop()

    return {
        "success": True,
        "message": "SSE subscriber stopped",
    }
