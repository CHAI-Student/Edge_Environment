"""
Event Recording Manager for Camera Driver

무게 변화 이벤트 발생 시 이미지와 영상을 저장하고
Node.js 오케스트레이터에 알림을 보냅니다.

Timeline:
    [--0.5s 전--][이벤트][------2.5s 후------]
                   ↑                          ↑
              트리거 시점              저장 & Node.js 알림

저장 구조:
    Edge_Environment/
    └── {YYYYMMDD_HHMMSS}/
        ├── images/
        │   ├── cam_0/snapshot.jpg
        │   ├── cam_1/snapshot.jpg
        │   └── ...
        └── videos/
            ├── cam_0/recording.mp4
            ├── cam_1/recording.mp4
            └── ...
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from dataclasses import dataclass, field

import aiohttp

# 한국 표준시 (KST, UTC+9)
KST = timezone(timedelta(hours=9))

if TYPE_CHECKING:
    from .manager import CameraManager
    from .sse_subscriber import WeightChangeEvent, DoorEvent

logger = logging.getLogger(__name__)


@dataclass
class MediaPaths:
    """미디어 파일 경로"""
    base_path: str
    session_id: str
    images: Dict[str, str] = field(default_factory=dict)
    videos: Dict[str, str] = field(default_factory=dict)


@dataclass
class PendingRecording:
    """대기 중인 녹화"""
    zone_id: int
    event_time: float
    trigger_time: float
    weight_data: Dict[str, Any]
    timer_task: Optional[asyncio.Task] = None


class EventRecordingManager:
    """
    이벤트 기반 녹화 관리자

    무게 변화 이벤트 발생 시:
    1. 이벤트 전 0.5초 프레임 마킹
    2. 이벤트 후 2.5초 대기
    3. 이미지 + 영상 저장
    4. Node.js에 media_paths 전송
    """

    def __init__(
        self,
        camera_manager: "CameraManager",
        pre_buffer_seconds: float = 0.5,
        post_buffer_seconds: float = 2.5,
        save_images: bool = True,
        save_videos: bool = True,
        nodejs_callback_url: str = "http://localhost:8888",
        media_base_path: Optional[str] = None,
    ):
        """
        초기화

        Args:
            camera_manager: 카메라 매니저 인스턴스
            pre_buffer_seconds: 이벤트 전 버퍼 시간 (초)
            post_buffer_seconds: 이벤트 후 녹화 시간 (초)
            save_images: 이미지 저장 여부
            save_videos: 영상 저장 여부
            nodejs_callback_url: Node.js 콜백 URL
            media_base_path: 미디어 저장 기본 경로
        """
        self._camera_manager = camera_manager
        self._pre_buffer_seconds = pre_buffer_seconds
        self._post_buffer_seconds = post_buffer_seconds
        self._save_images = save_images
        self._save_videos = save_videos
        self._nodejs_callback_url = nodejs_callback_url

        # 미디어 저장 경로 설정
        if media_base_path:
            # Resolve to absolute path to avoid relative-path surprises
            self._media_base_path = Path(media_base_path).resolve()
        else:
            # 기본: Edge_Environment/
            self._media_base_path = Path(__file__).parent.parent.parent.parent.resolve()

        # 대기 중인 녹화
        self._pending_recordings: Dict[int, PendingRecording] = {}

        # HTTP 세션
        self._http_session: Optional[aiohttp.ClientSession] = None

        # Zone → Camera 매핑 (config/zone_mapping.json에서 로드)
        self._zone_camera_map = self._load_zone_camera_mapping()

        # Top 카메라 영상 녹화 상태 (데드볼트 열림 시 시작)
        self._top_video_session_id: Optional[str] = None
        self._top_video_recording_task: Optional[asyncio.Task] = None
        self._top_video_stop_event = asyncio.Event()

        # 3초 촬영 설정
        self._timed_capture_duration = 3.0  # 3초
        self._timed_capture_interval = 0.1  # 0.1초 간격 (10fps, 약 30장)

    def _load_zone_camera_mapping(self) -> Dict[int, List[int]]:
        """
        config/zone_mapping.json에서 Zone-Camera 매핑 로드.

        Returns:
            Zone ID → Camera ID 리스트 매핑
        """
        # 기본값 (fallback)
        default_mapping = {
            0: [0, 1],  # Zone 0: Top(0) + Side(1)
            1: [0, 2],  # Zone 1: Top(0) + Side(2)
            2: [0, 3],  # Zone 2: Top(0) + Side(3)
            3: [0, 4],  # Zone 3: Top(0) + Side(4)
            4: [0, 5],  # Zone 4: Top(0) + Side(5)
        }

        # config 파일 경로 (Edge_Environment/config/zone_mapping.json)
        config_path = self._media_base_path / "config" / "zone_mapping.json"

        try:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                zone_mapping: Dict[int, List[int]] = {}
                top_camera_id = config.get("top_camera_id", 0)

                for zone_id_str, zone_info in config.get("zones", {}).items():
                    zone_id = int(zone_id_str)
                    side_camera_id = zone_info.get("side_camera_id", zone_id + 1)
                    zone_mapping[zone_id] = [top_camera_id, side_camera_id]

                logger.info(f"Zone-camera mapping loaded from {config_path}: {zone_mapping}")
                return zone_mapping

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse zone_mapping.json: {e}")
        except Exception as e:
            logger.warning(f"Failed to load zone_mapping.json: {e}")

        logger.info(f"Using default zone-camera mapping: {default_mapping}")
        return default_mapping

    async def on_door_change(self, event: "DoorEvent"):
        """
        도어/데드볼트 이벤트 처리

        Args:
            event: 도어 이벤트
        """
        deadbolt_state = event.deadbolt_state

        if deadbolt_state == "OPEN":
            # 데드볼트 열림 → Top 카메라 영상 녹화 시작
            await self._start_top_video_recording()
        elif deadbolt_state in ("CLOSED", "CLOSE"):
            # 데드볼트 닫힘 → Top 카메라 영상 녹화 중지
            await self._stop_top_video_recording()

    async def _start_top_video_recording(self):
        """
        Top 카메라 영상 녹화 시작 (데드볼트 열림 시)

        문이 닫힐 때까지 Top 카메라의 영상을 계속 녹화합니다.
        """
        if self._top_video_session_id:
            logger.warning("Top video recording already active")
            return

        # 세션 ID 생성
        self._top_video_session_id = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        session_path = self._media_base_path / self._top_video_session_id
        videos_path = session_path / "videos"
        videos_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Top video recording started: session={self._top_video_session_id}")

        # 녹화 태스크 시작
        self._top_video_stop_event.clear()
        self._top_video_recording_task = asyncio.create_task(
            self._top_video_recording_loop(videos_path)
        )

    async def _top_video_recording_loop(self, videos_path: Path):
        """
        Top 카메라 영상 녹화 루프

        Args:
            videos_path: 영상 저장 경로
        """
        try:
            import cv2

            camera = self._camera_manager.get_camera(0)  # Top camera
            if camera is None:
                logger.error("Top camera (0) not found")
                return

            # VideoWriter 설정
            video_path = videos_path / "cam_0.mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            fps = camera.config.fps if hasattr(camera, 'config') else 30
            resolution = (640, 480)  # 기본 해상도

            # 첫 프레임에서 해상도 확인
            frame = camera.get_frame()
            if frame is not None:
                height, width = frame.shape[:2]
                resolution = (width, height)

            writer = cv2.VideoWriter(str(video_path), fourcc, fps, resolution)

            if not writer.isOpened():
                logger.error(f"Failed to create VideoWriter for top camera")
                return

            frame_count = 0
            interval = 1.0 / fps

            logger.info(f"Top video recording loop started: {video_path}")

            while not self._top_video_stop_event.is_set():
                frame = camera.get_frame()
                if frame is not None:
                    writer.write(frame)
                    frame_count += 1

                    if frame_count % 100 == 0:
                        logger.debug(f"Top video: {frame_count} frames recorded")

                await asyncio.sleep(interval)

            writer.release()
            logger.info(f"Top video recording stopped: {frame_count} frames saved to {video_path}")

        except ImportError:
            logger.error("OpenCV not available for video recording")
        except asyncio.CancelledError:
            logger.info("Top video recording cancelled")
            raise
        except Exception as e:
            logger.error(f"Top video recording error: {e}")

    async def _stop_top_video_recording(self):
        """
        Top 카메라 영상 녹화 중지 (데드볼트 닫힘 시)
        """
        if not self._top_video_session_id:
            logger.debug("No active top video recording")
            return

        # 중지 신호
        self._top_video_stop_event.set()

        # 태스크 종료 대기
        if self._top_video_recording_task:
            try:
                await asyncio.wait_for(self._top_video_recording_task, timeout=2.0)
            except asyncio.TimeoutError:
                self._top_video_recording_task.cancel()
            except asyncio.CancelledError:
                pass
            self._top_video_recording_task = None

        logger.info(f"Top video recording stopped: session={self._top_video_session_id}")
        self._top_video_session_id = None

    async def on_weight_change(self, event: "WeightChangeEvent"):
        """
        무게 변화 이벤트 처리

        새로운 로직: 3초간 Top + Side 이미지 저장, Side 영상 녹화

        Args:
            event: 무게 변화 이벤트
        """
        zone_id = event.zone_id
        current_time = time.time()

        logger.info(f"Weight change event received: Zone {zone_id}, delta={event.delta}g")

        # 이미 대기 중인 녹화가 있으면 취소하고 새로 시작
        if zone_id in self._pending_recordings:
            pending = self._pending_recordings[zone_id]
            if pending.timer_task:
                pending.timer_task.cancel()
                logger.debug(f"Zone {zone_id}: Cancelled existing recording timer")

        # 무게 데이터 구성
        weight_data = {
            "before_weights": event.previous,
            "after_weights": event.current,
            "delta_weight": event.delta,
            "channels": event.channels,
        }

        # 녹화 예약
        pending = PendingRecording(
            zone_id=zone_id,
            event_time=current_time,
            trigger_time=current_time,
            weight_data=weight_data,
        )

        # 3초 촬영 태스크 시작 (즉시 시작, 3초 후 완료)
        pending.timer_task = asyncio.create_task(
            self._timed_capture(pending)
        )

        self._pending_recordings[zone_id] = pending
        logger.info(f"Zone {zone_id}: 3-second timed capture started")

    async def _timed_capture(self, pending: PendingRecording):
        """
        3초간 시간 제한 촬영 (무게 변화 시)

        Top + Side 카메라 이미지 저장 + Side 카메라 영상 녹화

        Args:
            pending: 대기 중인 녹화 정보
        """
        zone_id = pending.zone_id
        start_time = time.time()

        # 세션 ID (Top 영상 녹화 세션 사용, 없으면 새로 생성)
        session_id = self._top_video_session_id or datetime.now(KST).strftime("%Y%m%d_%H%M%S")

        # 저장 경로 생성
        session_path = self._media_base_path / session_id
        images_path = session_path / "images"
        videos_path = session_path / "videos"
        images_path.mkdir(parents=True, exist_ok=True)
        videos_path.mkdir(parents=True, exist_ok=True)

        # 카메라 ID (Top: 0, Side: zone_id + 1)
        top_cam_id = 0
        side_cam_id = zone_id + 1
        camera_ids = [top_cam_id, side_cam_id]

        logger.info(f"Zone {zone_id}: Timed capture started - cameras={camera_ids}, duration={self._timed_capture_duration}s, session_path={session_path}")

        try:
            import cv2

            # 카메라별 이미지 폴더 생성
            for cam_id in camera_ids:
                (images_path / f"cam_{cam_id}").mkdir(exist_ok=True)

            # Side 카메라 VideoWriter 설정
            side_camera = self._camera_manager.get_camera(side_cam_id)
            side_video_writer = None
            side_video_path = None

            if side_camera and self._save_videos:
                frame = side_camera.get_frame()
                if frame is not None:
                    height, width = frame.shape[:2]
                    side_video_path = videos_path / f"cam_{side_cam_id}.mp4"
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    fps = side_camera.config.fps if hasattr(side_camera, 'config') else 30
                    side_video_writer = cv2.VideoWriter(str(side_video_path), fourcc, fps, (width, height))

            # Log cameras availability for debugging
            for cam_id in camera_ids:
                cam = self._camera_manager.get_camera(cam_id)
                if cam is None:
                    logger.warning(f"Zone {zone_id}: Camera {cam_id} not found (will skip frames)")
                else:
                    logger.debug(f"Zone {zone_id}: Camera {cam_id} ready, buffer_size={getattr(cam, 'buffer_size', 'n/a')}")

            # 프레임 카운터
            frame_counts = {cam_id: 0 for cam_id in camera_ids}

            # 3초간 촬영 루프
            while (time.time() - start_time) < self._timed_capture_duration:
                for cam_id in camera_ids:
                    camera = self._camera_manager.get_camera(cam_id)
                    if camera is None:
                        continue

                    frame = camera.get_frame()
                    if frame is None:
                        logger.debug(f"Zone {zone_id}: Camera {cam_id} returned no frame at capture loop")
                        continue

                    # 이미지 저장
                    if self._save_images:
                        frame_counts[cam_id] += 1
                        img_path = images_path / f"cam_{cam_id}" / f"frame_{frame_counts[cam_id]:04d}.jpg"
                        cv2.imwrite(str(img_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

                    # Side 영상에 프레임 추가
                    if cam_id == side_cam_id and side_video_writer:
                        side_video_writer.write(frame)

                await asyncio.sleep(self._timed_capture_interval)

            # VideoWriter 정리
            if side_video_writer:
                side_video_writer.release()

            # 미디어 경로 정보
            media_paths = MediaPaths(
                base_path=str(session_path),
                session_id=session_id,
            )
            for cam_id in camera_ids:
                media_paths.images[f"cam_{cam_id}"] = str(images_path / f"cam_{cam_id}")
            if side_video_path:
                media_paths.videos[f"cam_{side_cam_id}"] = str(side_video_path)

            logger.info(
                f"Zone {zone_id}: Timed capture completed - "
                f"images={sum(frame_counts.values())}, video={'yes' if side_video_path else 'no'}"
            )

            # Node.js에 알림
            await self._notify_nodejs(zone_id, pending.weight_data, media_paths)

        except ImportError:
            logger.error("OpenCV not available for timed capture")
        except asyncio.CancelledError:
            logger.debug(f"Zone {zone_id}: Timed capture cancelled")
            raise
        except Exception as e:
            logger.error(f"Zone {zone_id}: Timed capture error - {e}")
        finally:
            # 정리
            if zone_id in self._pending_recordings:
                del self._pending_recordings[zone_id]

    async def _delayed_save(self, pending: PendingRecording):
        """
        지연 저장 (post_buffer_seconds 후) - 레거시 호환용

        Args:
            pending: 대기 중인 녹화 정보
        """
        try:
            await asyncio.sleep(self._post_buffer_seconds)
            await self._execute_save(pending)
        except asyncio.CancelledError:
            logger.debug(f"Zone {pending.zone_id}: Recording cancelled")
        except Exception as e:
            logger.error(f"Zone {pending.zone_id}: Save failed - {e}")
        finally:
            # 정리
            if pending.zone_id in self._pending_recordings:
                del self._pending_recordings[pending.zone_id]

    async def _execute_save(self, pending: PendingRecording):
        """
        이미지 및 영상 저장 실행

        Args:
            pending: 대기 중인 녹화 정보
        """
        zone_id = pending.zone_id
        event_time = pending.event_time
        current_time = time.time()

        # 세션 ID 생성 (YYYYMMDD_HHMMSS 형식, KST 기준)
        session_id = datetime.fromtimestamp(event_time, tz=KST).strftime("%Y%m%d_%H%M%S")

        # 저장 경로 생성
        session_path = self._media_base_path / session_id
        images_path = session_path / "images"
        videos_path = session_path / "videos"

        images_path.mkdir(parents=True, exist_ok=True)
        if self._save_videos:
            videos_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Zone {zone_id}: Saving media to {session_path}")

        # 프레임 시간 범위 계산
        start_time = event_time - self._pre_buffer_seconds
        end_time = current_time

        # 해당 Zone의 카메라들
        camera_ids = self._zone_camera_map.get(zone_id, [0, zone_id + 1])

        media_paths = MediaPaths(
            base_path=str(session_path),
            session_id=session_id,
        )

        # 각 카메라별 저장
        for cam_id in camera_ids:
            camera = self._camera_manager.get_camera(cam_id)
            if camera is None:
                logger.warning(f"Camera {cam_id} not found")
                continue

            cam_key = f"cam_{cam_id}"

            # 이미지 저장
            if self._save_images:
                image_path = await self._save_snapshot(
                    camera, images_path / cam_key, event_time
                )
                if image_path:
                    media_paths.images[cam_key] = str(image_path)

            # 영상 저장
            if self._save_videos:
                video_path = await self._save_video(
                    camera, videos_path / cam_key, start_time, end_time
                )
                if video_path:
                    media_paths.videos[cam_key] = str(video_path)

        # Node.js에 알림
        await self._notify_nodejs(zone_id, pending.weight_data, media_paths)

        logger.info(
            f"Zone {zone_id}: Media saved - "
            f"images={len(media_paths.images)}, videos={len(media_paths.videos)}"
        )

    async def _save_snapshot(
        self,
        camera,
        output_dir: Path,
        event_time: float,
    ) -> Optional[Path]:
        """
        스냅샷 이미지 저장

        Args:
            camera: 카메라 인스턴스
            output_dir: 출력 디렉토리
            event_time: 이벤트 시간

        Returns:
            저장된 파일 경로
        """
        try:
            import cv2

            output_dir.mkdir(parents=True, exist_ok=True)

            # 이벤트 시점에 가장 가까운 프레임 찾기
            frames = camera.get_frames_in_range(
                event_time - 0.5, event_time + 0.5
            )

            if not frames:
                # 버퍼에 없으면 현재 프레임 사용
                frame = camera.get_frame()
                if frame is None:
                    logger.warning(f"Camera {camera.camera_id}: No frame available")
                    return None
            else:
                # 이벤트 시점에 가장 가까운 프레임 선택
                best_frame = min(frames, key=lambda x: abs(x[0] - event_time))
                frame = best_frame[1]

            # 이미지 저장
            output_path = output_dir / "snapshot.jpg"
            cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

            logger.debug(f"Camera {camera.camera_id}: Snapshot saved to {output_path}")
            return output_path

        except ImportError:
            logger.warning("OpenCV not available for snapshot")
            return None
        except Exception as e:
            logger.error(f"Camera {camera.camera_id}: Snapshot save error - {e}")
            return None

    async def _save_video(
        self,
        camera,
        output_dir: Path,
        start_time: float,
        end_time: float,
    ) -> Optional[Path]:
        """
        영상 파일 저장

        Args:
            camera: 카메라 인스턴스
            output_dir: 출력 디렉토리
            start_time: 시작 시간
            end_time: 종료 시간

        Returns:
            저장된 파일 경로
        """
        try:
            import cv2

            output_dir.mkdir(parents=True, exist_ok=True)

            # 시간 범위의 프레임 가져오기
            frames = camera.get_frames_in_range(start_time, end_time)

            if not frames:
                logger.warning(f"Camera {camera.camera_id}: No frames in range")
                return None

            # 첫 프레임에서 크기 확인
            height, width = frames[0][1].shape[:2]

            # VideoWriter 설정
            output_path = output_dir / "recording.mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            fps = camera.config.fps

            writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

            # VideoWriter 생성 확인
            if not writer.isOpened():
                logger.error(f"Camera {camera.camera_id}: Failed to create VideoWriter")
                return None

            # 프레임 쓰기
            frames_written = 0
            for ts, frame in frames:
                if writer.write(frame):
                    frames_written += 1

            writer.release()

            # 최소 프레임 수 확인
            if frames_written == 0:
                logger.warning(f"Camera {camera.camera_id}: No frames written to video")
                # 빈 파일 삭제
                if output_path.exists():
                    output_path.unlink()
                return None

            duration = end_time - start_time
            logger.debug(
                f"Camera {camera.camera_id}: Video saved to {output_path} "
                f"({frames_written}/{len(frames)} frames, {duration:.1f}s)"
            )
            return output_path

        except ImportError:
            logger.warning("OpenCV not available for video")
            return None
        except Exception as e:
            logger.error(f"Camera {camera.camera_id}: Video save error - {e}")
            return None

    async def _notify_nodejs(
        self,
        zone_id: int,
        weight_data: Dict[str, Any],
        media_paths: MediaPaths,
    ):
        """
        Node.js 오케스트레이터에 알림

        Args:
            zone_id: Zone ID
            weight_data: 무게 데이터
            media_paths: 미디어 파일 경로
        """
        callback_url = f"{self._nodejs_callback_url}/api/camera/media-ready"

        payload = {
            "zone_id": zone_id,
            "session_id": media_paths.session_id,
            "weight_data": weight_data,
            "media_paths": {
                "base_path": media_paths.base_path,
                "images": media_paths.images,
                "videos": media_paths.videos,
            },
            "timestamp": time.time(),
        }

        session_created_here = False
        try:
            # 세션 가져오기 또는 생성
            if self._http_session is None or self._http_session.closed:
                self._http_session = aiohttp.ClientSession()
                session_created_here = True

            async with self._http_session.post(
                callback_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status == 200:
                    logger.info(f"Node.js notified: Zone {zone_id}, session={media_paths.session_id}")
                else:
                    logger.warning(f"Node.js notification failed: HTTP {response.status}")

        except aiohttp.ClientError as e:
            logger.error(f"Failed to notify Node.js: {e}")
            # 연결 오류 시 세션 리셋
            if session_created_here and self._http_session:
                try:
                    await self._http_session.close()
                except Exception:
                    pass
                self._http_session = None
        except Exception as e:
            logger.error(f"Unexpected error notifying Node.js: {e}")

    async def close(self):
        """리소스 정리"""
        # Top 영상 녹화 중지
        if self._top_video_session_id:
            await self._stop_top_video_recording()

        # 대기 중인 녹화 취소 (모든 태스크 취소 시도)
        for zone_id, pending in list(self._pending_recordings.items()):
            if pending.timer_task:
                try:
                    pending.timer_task.cancel()
                    # 태스크 완료 대기 (짧은 타임아웃)
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(pending.timer_task),
                            timeout=0.5
                        )
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
                except Exception as e:
                    logger.warning(f"Error cancelling task for zone {zone_id}: {e}")
        self._pending_recordings.clear()

        # HTTP 세션 종료
        if self._http_session:
            try:
                if not self._http_session.closed:
                    await self._http_session.close()
            except Exception as e:
                logger.warning(f"Error closing HTTP session: {e}")
            finally:
                self._http_session = None

        logger.info("EventRecordingManager closed")

    def get_status(self) -> Dict[str, Any]:
        """상태 조회"""
        return {
            "pending_recordings": list(self._pending_recordings.keys()),
            "pre_buffer_seconds": self._pre_buffer_seconds,
            "post_buffer_seconds": self._post_buffer_seconds,
            "save_images": self._save_images,
            "save_videos": self._save_videos,
            "nodejs_callback_url": self._nodejs_callback_url,
            "media_base_path": str(self._media_base_path),
            "top_video_recording": self._top_video_session_id is not None,
            "top_video_session_id": self._top_video_session_id,
            "timed_capture_duration": self._timed_capture_duration,
            "timed_capture_interval": self._timed_capture_interval,
        }
