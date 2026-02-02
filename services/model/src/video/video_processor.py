"""
Video Processor for AVI-based YOLO Inference.

Processes entire AVI videos frame-by-frame with YOLO inference
and aggregates results using voting-based ensemble.

Memory-efficient design for Jetson Orin Nano:
- FFmpeg subprocess with NVDEC hardware decoding
- Streaming frame extraction (one frame at a time)
- Immediate memory release after inference
- Only vote counts are accumulated (not images)

v4.1 추가:
- Bounding box 중심점 이동 추적 (Motion Tracking)
- 이동이 감지된 객체만 후보에 포함

Usage:
    processor = VideoProcessor(yolo=yolo_wrapper)
    results = processor.process_videos(
        top_path="/path/to/top.avi",
        side_path="/path/to/side.avi"
    )
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .frame_extractor import create_frame_extractor
from .voting_ensemble import VotingEnsemble, VoteResult
from vision import YOLOWrapper
from core.config import config

logger = logging.getLogger(__name__)


@dataclass
class BboxTracker:
    """
    Bounding box 중심점 이동 추적.

    각 class_id별로 첫 번째/마지막 bbox 중심점과 최대 이동 거리를 추적.

    Attributes:
        first_center: 첫 번째 감지 시 중심점 (x, y)
        last_center: 마지막 감지 시 중심점 (x, y)
        max_distance: 관찰된 최대 이동 거리 (픽셀)
        detection_count: 총 감지 횟수
        frame_indices: 감지된 프레임 인덱스 목록
        dynamic_threshold: bbox 크기 기반 동적 임계값 (픽셀)
    """
    first_center: Optional[Tuple[float, float]] = None
    last_center: Optional[Tuple[float, float]] = None
    max_distance: float = 0.0
    detection_count: int = 0
    frame_indices: List[int] = field(default_factory=list)
    dynamic_threshold: float = 0.0  # bbox 크기 기반 동적 임계값

    def update(self, center: Tuple[float, float], frame_idx: int) -> None:
        """bbox 중심점 업데이트."""
        if self.first_center is None:
            self.first_center = center

        # 이전 중심점과의 거리 계산
        if self.last_center is not None:
            distance = math.sqrt(
                (center[0] - self.last_center[0]) ** 2 +
                (center[1] - self.last_center[1]) ** 2
            )
            self.max_distance = max(self.max_distance, distance)

        self.last_center = center
        self.detection_count += 1
        self.frame_indices.append(frame_idx)

    @property
    def total_displacement(self) -> float:
        """첫 번째와 마지막 위치 간 총 이동 거리."""
        if self.first_center is None or self.last_center is None:
            return 0.0
        return math.sqrt(
            (self.last_center[0] - self.first_center[0]) ** 2 +
            (self.last_center[1] - self.first_center[1]) ** 2
        )

    def has_motion(self, min_displacement: float = 30.0) -> bool:
        """
        이동이 있었는지 여부.

        Args:
            min_displacement: 최소 이동 거리 임계값 (픽셀)

        Returns:
            이동이 감지되었으면 True
        """
        # 동적 임계값이 설정되어 있으면 사용, 아니면 기본값 사용
        threshold = self.dynamic_threshold if self.dynamic_threshold > 0 else min_displacement
        return self.total_displacement >= threshold or self.max_distance >= threshold


@dataclass
class VideoProcessingStats:
    """
    Video processing statistics.

    Attributes:
        top_frames: Number of frames processed from top camera
        side_frames: Number of frames processed from side camera
        top_detections: Total detections from top camera
        side_detections: Total detections from side camera
        processing_time_ms: Total processing time in milliseconds
        motion_filtered_classes: Number of classes filtered out due to no motion
    """
    top_frames: int = 0
    side_frames: int = 0
    top_detections: int = 0
    side_detections: int = 0
    processing_time_ms: float = 0.0
    motion_filtered_classes: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "top_frames": self.top_frames,
            "side_frames": self.side_frames,
            "top_detections": self.top_detections,
            "side_detections": self.side_detections,
            "total_frames": self.top_frames + self.side_frames,
            "total_detections": self.top_detections + self.side_detections,
            "processing_time_ms": round(self.processing_time_ms, 1),
            "motion_filtered_classes": self.motion_filtered_classes,
        }


@dataclass
class VideoProcessingResult:
    """
    Video processing result.

    Attributes:
        vote_results: Combined voting results from both cameras
        top_ensemble: Top camera voting ensemble
        side_ensemble: Side camera voting ensemble
        stats: Processing statistics
    """
    vote_results: List[VoteResult]
    top_ensemble: VotingEnsemble
    side_ensemble: VotingEnsemble
    stats: VideoProcessingStats

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "vote_results": [r.to_dict() for r in self.vote_results],
            "stats": self.stats.to_dict(),
        }


class VideoProcessor:
    """
    AVI video processor with YOLO inference and voting ensemble.

    Processes videos frame-by-frame to minimize memory usage,
    suitable for Jetson Orin Nano deployment.

    Uses FFmpeg with NVDEC hardware acceleration when available.
    """

    def __init__(
        self,
        yolo: YOLOWrapper,
        min_vote_ratio: float = 0.05,
        confidence_threshold: float = 0.6,
        use_hwaccel: bool = True,
        motion_filter_enabled: bool = True,
        min_motion_displacement: float = 30.0,
        side_roi_x_max: float = 240.0,
    ):
        """
        Initialize video processor.

        Args:
            yolo: YOLOWrapper instance for inference
            min_vote_ratio: Minimum vote ratio to include in results (default: 5%)
            confidence_threshold: Minimum confidence for YOLO detection (default: 0.6)
            use_hwaccel: Use hardware acceleration for video decoding (default: True)
            motion_filter_enabled: Enable motion-based filtering (default: True)
            min_motion_displacement: Minimum bbox center displacement to consider as motion (default: 30 pixels)
            side_roi_x_max: Side 카메라 ROI 최대 X 좌표 (기본 240px, 왼쪽 절반만 허용)
        """
        self.yolo = yolo
        self.min_vote_ratio = min_vote_ratio
        self.confidence_threshold = confidence_threshold
        self.use_hwaccel = use_hwaccel
        self.motion_filter_enabled = motion_filter_enabled
        self.min_motion_displacement = min_motion_displacement
        self.side_roi_x_max = side_roi_x_max

    def process_videos(
        self,
        top_path: Optional[str] = None,
        side_path: Optional[str] = None,
        top_weight: float = 0.5,
        side_weight: float = 0.5,
    ) -> VideoProcessingResult:
        """
        Process top and side camera videos.

        Args:
            top_path: Path to top camera AVI file (optional)
            side_path: Path to side camera AVI file (optional)
            top_weight: Weight for top camera in ensemble (default: 0.5)
            side_weight: Weight for side camera in ensemble (default: 0.5)

        Returns:
            VideoProcessingResult with combined voting results
        """
        start_time = time.time()
        stats = VideoProcessingStats()

        logger.info(f"[VIDEO] ========== 비디오 처리 시작 ==========")
        logger.info(f"[VIDEO] top_path={top_path}")
        logger.info(f"[VIDEO] side_path={side_path}")

        top_ensemble = VotingEnsemble(min_vote_ratio=self.min_vote_ratio)
        side_ensemble = VotingEnsemble(min_vote_ratio=self.min_vote_ratio)

        # Process top camera video
        if top_path:
            logger.info(f"[VIDEO] Top 카메라 처리 시작...")
            top_stats = self._process_single_video(top_path, top_ensemble, "top")
            stats.top_frames = top_stats["frames"]
            stats.top_detections = top_stats["detections"]
            stats.motion_filtered_classes += top_stats.get("motion_filtered", 0)
            logger.info(
                f"[VIDEO] Top 완료: 총 {stats.top_frames}프레임, "
                f"탐지={stats.top_detections}개, 고유클래스={len(top_ensemble.votes)}개"
            )

        # Process side camera video
        if side_path:
            logger.info(f"[VIDEO] Side 카메라 처리 시작...")
            side_stats = self._process_single_video(side_path, side_ensemble, "side")
            stats.side_frames = side_stats["frames"]
            stats.side_detections = side_stats["detections"]
            stats.motion_filtered_classes += side_stats.get("motion_filtered", 0)
            logger.info(
                f"[VIDEO] Side 완료: 총 {stats.side_frames}프레임, "
                f"탐지={stats.side_detections}개, 고유클래스={len(side_ensemble.votes)}개"
            )

        # Combine results with config weights
        combined_results = VotingEnsemble.combine(
            top_ensemble=top_ensemble,
            side_ensemble=side_ensemble,
            top_weight=config.top_weight,
            side_weight=config.side_weight,
            common_class_bonus=config.common_class_bonus,
        )

        # Filter by minimum vote ratio OR minimum vote count
        # 조건 1: vote_ratio >= 5% (기존)
        # 조건 2: vote_count >= 3 (절대값 3프레임 이상이면 포함 - 짧은 비디오 대응)
        min_vote_count = 3
        filtered_results = [
            r for r in combined_results
            if r.vote_ratio >= self.min_vote_ratio or r.vote_count >= min_vote_count
        ]

        # 필터링 로그
        filtered_by_ratio = sum(1 for r in combined_results if r.vote_ratio >= self.min_vote_ratio)
        filtered_by_count = sum(1 for r in combined_results if r.vote_count >= min_vote_count and r.vote_ratio < self.min_vote_ratio)
        logger.info(
            f"[VIDEO] 필터링: vote_ratio >= {self.min_vote_ratio*100:.0f}%: {filtered_by_ratio}개, "
            f"vote_count >= {min_vote_count}: 추가 {filtered_by_count}개"
        )

        stats.processing_time_ms = (time.time() - start_time) * 1000

        logger.info(f"[VIDEO] 앙상블 결합 완료: {len(filtered_results)}개 후보")

        return VideoProcessingResult(
            vote_results=filtered_results,
            top_ensemble=top_ensemble,
            side_ensemble=side_ensemble,
            stats=stats,
        )

    def _process_single_video(
        self,
        video_path: str,
        ensemble: VotingEnsemble,
        camera_type: str = "unknown",
    ) -> dict:
        """
        Process a single video file with motion-based filtering.

        Uses FFmpeg for hardware-accelerated decoding (NVDEC on Jetson).
        Streams frames one at a time to minimize memory usage.
        Each frame is immediately released after YOLO inference.

        Motion Tracking (v4.1):
        - Tracks bbox center points for each class across frames
        - Only includes classes with significant center movement in final results
        - Filters out stationary background objects

        Args:
            video_path: Path to video file
            ensemble: VotingEnsemble to accumulate votes
            camera_type: Camera type for logging ("top" or "side")

        Returns:
            Statistics dict with frames, detections, and motion_filtered count
        """
        frame_count = 0
        detection_count = 0

        # Motion tracking: class_id -> BboxTracker
        bbox_trackers: Dict[int, BboxTracker] = {}

        # Temporary storage for votes (applied after motion filtering)
        # class_id -> list of (confidence, class_name) tuples
        pending_votes: Dict[int, List[Tuple[float, str]]] = {}

        # Use factory to get appropriate extractor (ffmpeg or cv2 fallback)
        extractor = create_frame_extractor(
            video_path,
            prefer_ffmpeg=True,
            use_hwaccel=self.use_hwaccel,
        )

        # ROI 필터링 통계
        roi_filtered_count = 0

        for frame in extractor:
            frame_count += 1

            # YOLO inference (single frame)
            detections = self.yolo.detect(frame)

            # Process detections
            for det in detections:
                # Filter out hands and low confidence
                if det.is_hand:
                    continue
                if det.conf < self.confidence_threshold:
                    continue

                # Side 카메라 ROI 필터: 왼쪽 영역만 허용
                # bbox 중심점이 오른쪽 영역(> side_roi_x_max)에 있으면 제외
                if camera_type == "side":
                    center_x = det.center[0]
                    if center_x > self.side_roi_x_max:
                        roi_filtered_count += 1
                        continue

                class_id = det.cls

                # Use YOLODetection's center property
                center = det.center

                # bbox 크기 기반 동적 임계값 계산
                bbox_width = det.x2 - det.x1
                bbox_height = det.y2 - det.y1
                bbox_size = max(bbox_width, bbox_height)
                # 동적 임계값: bbox 크기의 10%, 최소 15px
                dynamic_threshold = max(15.0, bbox_size * 0.10)

                # Update bbox tracker
                if class_id not in bbox_trackers:
                    bbox_trackers[class_id] = BboxTracker()
                bbox_trackers[class_id].update(center, frame_count)
                # 동적 임계값 업데이트 (최대값 유지)
                bbox_trackers[class_id].dynamic_threshold = max(
                    bbox_trackers[class_id].dynamic_threshold,
                    dynamic_threshold
                )

                # Store vote for later (will be applied after motion filtering)
                if class_id not in pending_votes:
                    pending_votes[class_id] = []
                pending_votes[class_id].append((det.conf, det.name))

                detection_count += 1

            # Log progress every 50 frames
            if frame_count % 50 == 0:
                logger.info(
                    f"[VIDEO] {camera_type} 처리 중: {frame_count}프레임, "
                    f"탐지={detection_count}개"
                )

        # Set frame count
        ensemble.set_frame_count(frame_count)

        # Apply motion filtering and add votes to ensemble
        motion_filtered_count = 0
        motion_passed_count = 0

        for class_id, votes in pending_votes.items():
            tracker = bbox_trackers.get(class_id)

            # Check motion
            has_motion = True
            if self.motion_filter_enabled and tracker is not None:
                has_motion = tracker.has_motion(self.min_motion_displacement)

            if has_motion:
                # Add all votes for this class
                for conf, class_name in votes:
                    ensemble.add_vote(
                        class_id=class_id,
                        confidence=conf,
                        class_name=class_name,
                    )
                motion_passed_count += 1

                if tracker:
                    threshold_used = tracker.dynamic_threshold if tracker.dynamic_threshold > 0 else self.min_motion_displacement
                    logger.debug(
                        f"[MOTION] {camera_type} class {class_id}: PASSED "
                        f"(displacement={tracker.total_displacement:.1f}px, "
                        f"max_dist={tracker.max_distance:.1f}px, "
                        f"threshold={threshold_used:.1f}px, "
                        f"detections={tracker.detection_count})"
                    )
            else:
                motion_filtered_count += 1
                if tracker:
                    threshold_used = tracker.dynamic_threshold if tracker.dynamic_threshold > 0 else self.min_motion_displacement
                    logger.info(
                        f"[MOTION] {camera_type} class {class_id}: FILTERED "
                        f"(displacement={tracker.total_displacement:.1f}px < threshold={threshold_used:.1f}px, "
                        f"detections={tracker.detection_count})"
                    )

        logger.info(
            f"[MOTION] {camera_type} 필터링 결과: "
            f"통과={motion_passed_count}개, 제외={motion_filtered_count}개 "
            f"(기본 임계값={self.min_motion_displacement}px, 동적 임계값 적용)"
        )

        # Side 카메라 ROI 필터링 결과 로그
        if camera_type == "side" and roi_filtered_count > 0:
            logger.info(
                f"[ROI] {camera_type} ROI 필터링: "
                f"{roi_filtered_count}개 탐지 제외 (center_x > {self.side_roi_x_max}px)"
            )

        return {
            "frames": frame_count,
            "detections": detection_count,
            "motion_filtered": motion_filtered_count,
            "roi_filtered": roi_filtered_count,
        }

    def process_single_video_file(
        self,
        video_path: str,
    ) -> VideoProcessingResult:
        """
        Process a single video file (for testing or single-camera setups).

        Args:
            video_path: Path to video file

        Returns:
            VideoProcessingResult with voting results
        """
        return self.process_videos(top_path=video_path)
