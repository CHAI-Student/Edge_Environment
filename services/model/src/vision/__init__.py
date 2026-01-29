"""
Vision module for YOLO inference and hand-proximity filtering.

YOLO 추론 및 손 근접 필터링 모듈.

파이프라인:
1. YOLOWrapper: YOLO 추론
2. HandProximityFilter: 손 근접 필터링
3. MotionCorrelationFilter: 손-상품 움직임 상관관계 분석
4. Top5Extractor: Top-K 후보 추출
5. MultiViewEnsemble: Top+Side 카메라 앙상블
"""

from .yolo_wrapper import YOLOWrapper, YOLODetection
from .hand_filter import HandProximityFilter, FilterResult
from .top5_extractor import Top5Extractor, ExtractionResult
from .multi_view_ensemble import MultiViewEnsemble
from .multi_hand_detector import MultiHandDetector, HandCluster, MultiHandFilterResult
from .motion_correlation_filter import (
    MotionCorrelationFilter,
    MotionCorrelationResult,
    MotionVector,
    TrackedObject,
    get_motion_filter,
    reset_motion_filter,
)

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
    # Motion Correlation (hand-product movement tracking)
    "MotionCorrelationFilter",
    "MotionCorrelationResult",
    "MotionVector",
    "TrackedObject",
    "get_motion_filter",
    "reset_motion_filter",
]
