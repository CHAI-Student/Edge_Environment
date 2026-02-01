"""
Vision module for YOLO inference and hand-proximity filtering (v4.0).

YOLO 추론 및 손 근접 필터링 모듈.

파이프라인:
1. YOLOWrapper: YOLO TensorRT 추론
2. HandProximityFilter: 손 근접 필터링
3. Top5Extractor: Top-K 후보 추출

v4.0 변경사항:
- MultiViewEnsemble 제거 (video/voting_ensemble.py로 통합)
- MultiHandDetector 제거
- MotionCorrelationFilter 제거
"""

from .yolo_wrapper import YOLOWrapper, YOLODetection
from .hand_filter import HandProximityFilter, FilterResult
from .top5_extractor import Top5Extractor, ExtractionResult

__all__ = [
    "YOLOWrapper",
    "YOLODetection",
    "HandProximityFilter",
    "FilterResult",
    "Top5Extractor",
    "ExtractionResult",
]
