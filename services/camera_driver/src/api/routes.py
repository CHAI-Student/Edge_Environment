"""
Camera Driver API Routes
"""

import io
import logging
import shutil
import time
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)

from config import (
    settings,
    ZONE_CAMERA_MAP,
    TOP_CAMERA_ID,
    ALL_CAMERA_IDS,
    get_physical_device_index,
    get_enabled_zones,
    get_max_zone_id,
    is_zone_enabled,
    get_kst_now,
)
from core import CameraManager
from models import (
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
        test_session = get_kst_now().strftime("%Y%m%d_%H%M%S_healthcheck")
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


def _test_image_save(manager) -> dict:
    """
    실제 이미지 저장 테스트.

    각 카메라에서 프레임을 캡처하고 JPEG로 저장한 후 파일을 확인합니다.

    Returns:
        {
            "success": bool,
            "cameras_tested": int,
            "cameras_passed": int,
            "details": {camera_id: {"captured": bool, "saved": bool, "verified": bool}}
        }
    """
    import cv2
    import os

    project_root = Path(__file__).parent.parent.parent.parent
    test_session = get_kst_now().strftime("%Y%m%d_%H%M%S_imgtest")
    test_path = project_root / test_session / "images"

    results = {
        "success": False,
        "cameras_tested": 0,
        "cameras_passed": 0,
        "details": {}
    }

    try:
        test_path.mkdir(parents=True, exist_ok=True)

        for camera_id in ALL_CAMERA_IDS:
            detail = {"captured": False, "saved": False, "verified": False}
            results["cameras_tested"] += 1

            try:
                # 1. 프레임 캡처
                frame = manager.get_frame(camera_id)
                if frame is None:
                    results["details"][camera_id] = detail
                    continue
                detail["captured"] = True

                # 2. JPEG 저장
                img_path = test_path / f"cam_{camera_id}_test.jpg"
                encode_result = cv2.imwrite(
                    str(img_path),
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 90]
                )
                if not encode_result:
                    results["details"][camera_id] = detail
                    continue
                detail["saved"] = True

                # 3. 파일 확인 (존재 + 크기 > 0)
                if img_path.exists() and os.path.getsize(img_path) > 0:
                    detail["verified"] = True
                    results["cameras_passed"] += 1

            except Exception as e:
                logger.warning(f"Image save test failed for camera {camera_id}: {e}")

            results["details"][camera_id] = detail

        # 전체 성공 여부
        results["success"] = (
            results["cameras_tested"] > 0 and
            results["cameras_passed"] == results["cameras_tested"]
        )

    except Exception as e:
        logger.error(f"Image save test error: {e}")
    finally:
        # 테스트 파일 정리
        try:
            if test_path.exists():
                shutil.rmtree(project_root / test_session)
        except Exception:
            pass

    return results


@router.get("/health")
async def health_check(request: Request = None) -> CameraHealthResponse:
    """Health check endpoint (카메라 초기화 상태 포함)."""
    # 저장 경로 쓰기 테스트만 수행 (블로킹 없음)
    storage_ok = _test_storage_writable()

    # 카메라 초기화 상태 확인
    manager = get_manager()
    cameras_initialized = manager.is_initialized
    cameras_connected = manager.connected_count

    # event_ready 상태 확인 (SSE 구독 및 이벤트 매니저 준비 완료)
    event_ready = False
    if request and hasattr(request.app, "state"):
        event_ready = getattr(request.app.state, "event_ready", False)

    # 카메라가 초기화되고 최소 1개 이상 연결되어야 HEALTHY
    cameras_healthy = cameras_initialized and cameras_connected > 0

    return CameraHealthResponse(
        cameras="HEALTHY" if cameras_healthy else "INITIALIZING",
        storage="HEALTHY" if storage_ok else "UNHEALTHY",
        cameras_initialized=cameras_initialized,
        cameras_connected=cameras_connected,
        event_ready=event_ready,
    )


@router.get("/health/detailed")
async def health_check_detailed() -> CameraHealthResponse:
    """Detailed health check (카메라 프레임 캡처 테스트 포함, 느릴 수 있음)."""
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

    # 3. 실제 이미지 저장 테스트 (프레임 캡처 → JPEG 저장 → 파일 확인)
    image_save_result = _test_image_save(manager)

    return CameraHealthResponse(
        cameras="HEALTHY" if all_cameras_ok else "UNHEALTHY",
        storage="HEALTHY" if storage_ok else "UNHEALTHY",
        image_save="HEALTHY" if image_save_result["success"] else "UNHEALTHY",
        image_save_details={
            "cameras_tested": image_save_result["cameras_tested"],
            "cameras_passed": image_save_result["cameras_passed"],
            "details": image_save_result["details"],
        },
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
    from config import ZONE_CONFIG

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
    base_path: Optional[str] = None  # Node.js에서 지정하는 저장 경로


class ContinuousCaptureRequest(BaseModel):
    """연속 촬영 요청."""
    session_id: Optional[str] = None
    camera_ids: Optional[list] = None  # 기본: [0] = Top 카메라
    interval: float = 0.5  # 촬영 간격 (초)
    include_video: bool = True  # 영상도 함께 녹화
    duration: Optional[float] = None  # 촬영 시간 (초, None이면 수동 중지까지)
    save_images: bool = True  # 이미지 저장 여부


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

    # Node.js에서 지정한 base_path 우선 사용, 없으면 기본값
    if request.base_path:
        effective_base_path = Path(request.base_path)
    elif settings.media_base_path:
        effective_base_path = Path(settings.media_base_path)
    else:
        effective_base_path = Path("data/")

    # 스냅샷 캡처 (기존 메서드 활용)
    saved_paths = manager.capture_snapshot(
        session_id=request.session_id,
        zone_id=zone_id,
        all_cameras=False,
        base_path=str(effective_base_path),  # Node.js 지정 경로 전달
    )

    # 세션 경로 계산
    session_path = str(effective_base_path / request.session_id / "images")

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


class RecordingStartRequest(BaseModel):
    """녹화 시작 요청."""
    zone_id: Optional[int] = None  # Zone ID (0-4, None이면 전체)
    include_top: bool = True  # Top 카메라 포함 여부
    record_video: bool = True  # 영상 녹화 여부
    base_path: Optional[str] = None  # 저장 기본 경로
    session_id: Optional[str] = None  # 세션 ID (없으면 자동 생성)
    top_only: bool = False  # Top 카메라만 녹화 (데드볼트 열림 시)
    duration: Optional[float] = None  # 촬영 시간 (초, None이면 수동 중지)
    save_images: bool = True  # 이미지도 저장할지 여부
    camera_ids: Optional[list] = None  # 특정 카메라 ID 목록


@router.post("/recording/start")
async def start_recording(
    request: RecordingStartRequest = None,
    request_obj: Request = None,
    # Query parameters for Node.js compatibility
    zone_id: Optional[int] = None,
    include_top: bool = True,
    record_video: bool = True,
    base_path: Optional[str] = None,
    session_id: Optional[str] = None,
    top_only: bool = False,
    duration: Optional[float] = None,
    save_images: bool = True,
    camera_ids: Optional[str] = None,  # comma-separated for query params
) -> dict:
    """
    녹화 시작.

    Query parameters 또는 JSON body 모두 지원합니다.
    Node.js는 query parameters로 보내므로 이를 우선 처리합니다.

    Query Params (Node.js 형식):
        - zone_id: Zone ID (0-4, None이면 전체)
        - include_top: Top 카메라 포함 여부
        - record_video: 영상 녹화 여부
        - base_path: 저장 기본 경로 (Node.js가 지정하는 전체 경로)
        - session_id: 세션 ID (없으면 자동 생성)
        - top_only: Top 카메라만 녹화 (데드볼트 열림 시)

    JSON Body (RecordingStartRequest):
        위와 동일한 필드를 JSON으로 전달

    Returns:
        세션 ID 및 경로 정보
    """
    manager = get_manager()

    # =========================================================================
    # 카메라 초기화 완료 대기 (최대 10초)
    # =========================================================================
    max_wait_seconds = 10.0
    wait_step = 0.3
    waited = 0.0

    while not manager.is_initialized and waited < max_wait_seconds:
        if waited == 0:
            logger.info("Waiting for camera initialization to complete...")
        await asyncio.sleep(wait_step)
        waited += wait_step

    if not manager.is_initialized:
        logger.warning(f"Camera initialization not complete after {max_wait_seconds}s, proceeding anyway")
    else:
        # 카메라가 초기화되었으면 스트리밍도 확인
        if not manager.is_streaming:
            logger.info("Cameras initialized but not streaming, starting streaming...")
            try:
                await asyncio.to_thread(manager.start_streaming)
            except Exception as e:
                logger.error(f"Failed to start streaming: {e}")

        # 추가로 카메라 연결 확인 (최대 3초)
        camera_wait = 0.0
        while manager.connected_count == 0 and camera_wait < 3.0:
            await asyncio.sleep(0.2)
            camera_wait += 0.2

        if manager.connected_count > 0:
            logger.info(f"Cameras ready: {manager.connected_count} connected after {waited:.1f}s wait")

    # Query params가 우선, 없으면 JSON body 사용
    effective_zone_id = zone_id
    effective_include_top = include_top
    effective_record_video = record_video
    effective_base_path = base_path
    effective_session_id = session_id
    effective_top_only = top_only
    effective_duration = duration
    effective_save_images = save_images
    effective_camera_ids = None

    # Parse camera_ids from comma-separated string (query param)
    if camera_ids:
        try:
            effective_camera_ids = [int(x.strip()) for x in camera_ids.split(",")]
        except ValueError:
            pass

    # JSON body 값 사용 (query param이 기본값인 경우)
    if request:
        if zone_id is None:
            effective_zone_id = request.zone_id
        if include_top is True and request.include_top is False:
            effective_include_top = request.include_top
        if record_video is True and request.record_video is False:
            effective_record_video = request.record_video
        if base_path is None:
            effective_base_path = request.base_path
        if session_id is None:
            effective_session_id = request.session_id
        if top_only is False and request.top_only is True:
            effective_top_only = request.top_only
        if duration is None:
            effective_duration = request.duration
        if save_images is False and request.save_images is True:
            effective_save_images = request.save_images
        if effective_camera_ids is None:
            effective_camera_ids = request.camera_ids

    logger.info(f"Recording start - base_path: {effective_base_path}, zone_id: {effective_zone_id}, include_top: {effective_include_top}")

    # base_path가 Node.js에서 지정한 전체 경로면 그대로 사용
    # 예: /home/chai/Documents/Edge_Environment/20260129_234150
    if effective_base_path:
        # base_path가 세션 폴더까지 포함된 전체 경로인 경우
        # 이미지는 base_path/images/cam{N}/ 에 저장
        manager.init_media_recorder(base_path=effective_base_path)
    elif not manager._media_recorder:
        manager.init_media_recorder()

    # Top 카메라만 녹화 모드 (데드볼트 열림 시)
    if effective_top_only:
        result = manager.start_top_video_only(session_id=effective_session_id)
        return {
            "success": True,
            "mode": "top_only",
            **result,
            "timestamp": time.time(),
        }

    # 시간 제한 촬영 모드 (무게 변화 시)
    if effective_duration is not None and effective_camera_ids:
        result = manager.start_timed_capture(
            session_id=effective_session_id,
            camera_ids=effective_camera_ids,
            duration=effective_duration,
            save_images=effective_save_images,
            save_side_video=effective_record_video,
        )
        return {
            "success": True,
            "mode": "timed",
            **result,
            "timestamp": time.time(),
        }

    # Node.js가 base_path를 지정한 경우: 연속 촬영 모드 (이미지 + 영상 동시 저장)
    # 이렇게 해야 Model 서비스가 이미지를 사용할 수 있음
    if effective_base_path:
        # 카메라 목록 결정
        camera_ids = []
        if effective_include_top:
            camera_ids.append(TOP_CAMERA_ID)  # 0 = Top camera
        if effective_zone_id is not None:
            camera_ids.append(effective_zone_id + 1)  # Zone 0 → cam_1

        # 세션 ID는 base_path의 마지막 폴더 이름
        from pathlib import Path
        session_id_from_path = Path(effective_base_path).name

        result = manager.start_continuous_capture(
            session_id=session_id_from_path,
            camera_ids=camera_ids,
            interval=0.5,  # 0.5초 간격으로 이미지 캡처
            include_video=effective_record_video,
            use_base_path_directly=True,  # Node.js 경로 직접 사용
        )

        return {
            "success": True,
            "mode": "continuous",
            "session_id": result.get("session_id"),
            "zone_id": effective_zone_id,
            "record_video": effective_record_video,
            "base_path": effective_base_path,
            "cameras": camera_ids,
            "interval": result.get("interval"),
            "paths": result.get("paths", {}),
            "timestamp": time.time(),
        }

    # 일반 녹화 모드 (base_path 없을 때)
    result_session_id = manager.start_recording(
        zone_id=effective_zone_id,
        include_top=effective_include_top,
        record_video=effective_record_video,
        use_base_path_directly=False,
    )

    if not result_session_id:
        raise HTTPException(status_code=500, detail="Failed to start recording")

    paths = manager.get_recording_paths(result_session_id)

    return {
        "success": True,
        "mode": "normal",
        "session_id": result_session_id,
        "zone_id": effective_zone_id,
        "record_video": effective_record_video,
        "base_path": effective_base_path,
        "paths": paths,
    }


class RecordingStopRequest(BaseModel):
    """녹화 중지 요청."""
    top_only: bool = False  # Top 카메라만 녹화 중지


@router.post("/recording/stop")
async def stop_recording(request: RecordingStopRequest = None) -> dict:
    """
    녹화 중지.

    Args:
        request: 중지 옵션
            - top_only: Top 카메라만 녹화 중지 (데드볼트 닫힘 시)

    Returns:
        세션 정보 (저장된 파일 경로 등)
    """
    manager = get_manager()

    # request가 None이면 기본값 사용
    if request is None:
        request = RecordingStopRequest()

    # Top 카메라만 녹화 중지 모드
    if request.top_only:
        if not manager.is_top_video_recording:
            raise HTTPException(status_code=400, detail="No active top video recording")

        result = manager.stop_top_video_only()
        return {
            "success": True,
            "mode": "top_only",
            "session_info": result,
            "timestamp": time.time(),
        }

    # 연속 촬영 중지 (Node.js 모드)
    if manager.is_continuous_capture_active:
        result = manager.stop_continuous_capture()
        return {
            "success": True,
            "mode": "continuous",
            "session_info": result,
            "timestamp": time.time(),
        }

    # 일반 녹화 중지
    if not manager.is_recording:
        raise HTTPException(status_code=400, detail="No active recording")

    result = manager.stop_recording()

    if not result:
        raise HTTPException(status_code=500, detail="Failed to stop recording")

    return {
        "success": True,
        "mode": "normal",
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

    top_video_session = getattr(manager, '_top_video_session_id', None)

    return {
        "is_recording": manager.is_recording,
        "is_top_video_recording": manager.is_top_video_recording,
        "top_video_session_id": top_video_session,
        "has_media_recorder": manager._media_recorder is not None,
        "timestamp": time.time(),
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


# =========================================================================
# 연속 촬영 API (문이 열려있는 동안 계속 이미지 저장)
# =========================================================================


@router.post("/continuous-capture/start")
async def start_continuous_capture(request: ContinuousCaptureRequest) -> dict:
    """
    연속 촬영 시작.

    데드볼트가 열릴 때 호출하여 문이 닫힐 때까지
    지정된 간격으로 이미지를 계속 저장합니다.

    Args:
        request: 연속 촬영 요청 (session_id, camera_ids, interval, include_video)

    Returns:
        {
            "success": True,
            "session_id": str,
            "cameras": List[int],
            "interval": float,
            "paths": Dict[str, str]
        }
    """
    manager = get_manager()

    result = manager.start_continuous_capture(
        session_id=request.session_id,
        camera_ids=request.camera_ids,
        interval=request.interval,
        include_video=request.include_video,
    )

    return {
        "success": True,
        **result,
        "timestamp": time.time(),
    }


@router.post("/continuous-capture/stop")
async def stop_continuous_capture() -> dict:
    """
    연속 촬영 중지.

    데드볼트가 닫힐 때 호출하여 연속 촬영을 중지하고
    저장된 미디어 경로를 반환합니다.

    Returns:
        {
            "success": True,
            "session_info": {
                "session_id": str,
                "base_path": str,
                "frame_counts": Dict[int, int],
                "video_paths": Dict[int, str],
                ...
            }
        }
    """
    manager = get_manager()

    if not manager.is_continuous_capture_active:
        raise HTTPException(status_code=400, detail="No active continuous capture")

    result = manager.stop_continuous_capture()

    return {
        "success": True,
        "session_info": result,
        "timestamp": time.time(),
    }


@router.get("/continuous-capture/status")
async def get_continuous_capture_status() -> dict:
    """
    연속 촬영 상태 조회.

    Returns:
        {
            "active": bool,
            "session_id": str | None,
            "interval": float
        }
    """
    manager = get_manager()

    return {
        **manager.get_continuous_capture_status(),
        "timestamp": time.time(),
    }
