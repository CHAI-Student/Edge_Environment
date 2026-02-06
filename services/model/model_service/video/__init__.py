"""
Video processing module for AVI file analysis.

Provides streaming frame extraction, YOLO inference, and voting-based ensemble.
Uses FFmpeg for hardware-accelerated decoding (NVDEC) on Jetson.
"""

from .frame_extractor import (
    StreamingFrameExtractor,
    CV2FrameExtractor,
    create_frame_extractor,
)
from .voting_ensemble import VoteCount, VoteResult, VotingEnsemble
from .video_processor import VideoProcessor

__all__ = [
    "StreamingFrameExtractor",
    "CV2FrameExtractor",
    "create_frame_extractor",
    "VoteCount",
    "VoteResult",
    "VotingEnsemble",
    "VideoProcessor",
]
