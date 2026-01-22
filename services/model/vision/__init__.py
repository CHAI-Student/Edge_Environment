"""
Vision module for YOLO inference and hand-proximity filtering.

YOLO 추론 및 손 근접 필터링 모듈.
"""

from .yolo_wrapper import YOLOWrapper, YOLODetection
from .hand_filter import HandProximityFilter, FilterResult
from .top5_extractor import Top5Extractor, ExtractionResult
from .multi_view_ensemble import MultiViewEnsemble
from .multi_hand_detector import MultiHandDetector, HandCluster, MultiHandFilterResult

__all__ = [
    "YOLOWrapper",
    "YOLODetection",
    "HandProximityFilter",
    "FilterResult",
    "Top5Extractor",
    "ExtractionResult",
    "MultiViewEnsemble",
    # Multi-hand detection (for multi-person scenarios)
    "MultiHandDetector",
    "HandCluster",
    "MultiHandFilterResult",
]
