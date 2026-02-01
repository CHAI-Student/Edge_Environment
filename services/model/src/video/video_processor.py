"""
Video Processor for AVI-based YOLO Inference.

Processes entire AVI videos frame-by-frame with YOLO inference
and aggregates results using voting-based ensemble.

Memory-efficient design for Jetson Orin Nano:
- FFmpeg subprocess with NVDEC hardware decoding
- Streaming frame extraction (one frame at a time)
- Immediate memory release after inference
- Only vote counts are accumulated (not images)

Usage:
    processor = VideoProcessor(yolo=yolo_wrapper)
    results = processor.process_videos(
        top_path="/path/to/top.avi",
        side_path="/path/to/side.avi"
    )
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from .frame_extractor import create_frame_extractor
from .voting_ensemble import VotingEnsemble, VoteResult
from vision import YOLOWrapper
from core.config import config

logger = logging.getLogger(__name__)


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
    """
    top_frames: int = 0
    side_frames: int = 0
    top_detections: int = 0
    side_detections: int = 0
    processing_time_ms: float = 0.0

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
        confidence_threshold: float = 0.3,
        use_hwaccel: bool = True,
    ):
        """
        Initialize video processor.

        Args:
            yolo: YOLOWrapper instance for inference
            min_vote_ratio: Minimum vote ratio to include in results (default: 5%)
            confidence_threshold: Minimum confidence for detection (default: 0.3)
            use_hwaccel: Use hardware acceleration for video decoding (default: True)
        """
        self.yolo = yolo
        self.min_vote_ratio = min_vote_ratio
        self.confidence_threshold = confidence_threshold
        self.use_hwaccel = use_hwaccel

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

        top_ensemble = VotingEnsemble(min_vote_ratio=self.min_vote_ratio)
        side_ensemble = VotingEnsemble(min_vote_ratio=self.min_vote_ratio)

        # Process top camera video
        if top_path:
            logger.info(f"Processing top camera video: {top_path}")
            top_stats = self._process_single_video(top_path, top_ensemble)
            stats.top_frames = top_stats["frames"]
            stats.top_detections = top_stats["detections"]
            logger.info(
                f"Top camera: {stats.top_frames} frames, "
                f"{stats.top_detections} detections"
            )

        # Process side camera video
        if side_path:
            logger.info(f"Processing side camera video: {side_path}")
            side_stats = self._process_single_video(side_path, side_ensemble)
            stats.side_frames = side_stats["frames"]
            stats.side_detections = side_stats["detections"]
            logger.info(
                f"Side camera: {stats.side_frames} frames, "
                f"{stats.side_detections} detections"
            )

        # Combine results with config weights
        combined_results = VotingEnsemble.combine(
            top_ensemble=top_ensemble,
            side_ensemble=side_ensemble,
            top_weight=config.top_weight,
            side_weight=config.side_weight,
            common_class_bonus=config.common_class_bonus,
        )

        # Filter by minimum vote ratio
        filtered_results = [
            r for r in combined_results
            if r.vote_ratio >= self.min_vote_ratio
        ]

        stats.processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Video processing complete: "
            f"{stats.top_frames + stats.side_frames} total frames, "
            f"{len(filtered_results)} product candidates, "
            f"{stats.processing_time_ms:.1f}ms"
        )

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
    ) -> dict:
        """
        Process a single video file.

        Uses FFmpeg for hardware-accelerated decoding (NVDEC on Jetson).
        Streams frames one at a time to minimize memory usage.
        Each frame is immediately released after YOLO inference.

        Args:
            video_path: Path to video file
            ensemble: VotingEnsemble to accumulate votes

        Returns:
            Statistics dict with frames and detections count
        """
        frame_count = 0
        detection_count = 0

        # Use factory to get appropriate extractor (ffmpeg or cv2 fallback)
        extractor = create_frame_extractor(
            video_path,
            prefer_ffmpeg=True,
            use_hwaccel=self.use_hwaccel,
        )

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

                # Add vote
                ensemble.add_vote(
                    class_id=det.cls,
                    confidence=det.conf,
                    class_name=det.name,
                )
                detection_count += 1

            # Frame is automatically released when loop continues
            ensemble.increment_frame_count()

            # Log progress every 100 frames
            if frame_count % 100 == 0:
                logger.debug(f"Processed {frame_count} frames...")

        return {
            "frames": frame_count,
            "detections": detection_count,
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
