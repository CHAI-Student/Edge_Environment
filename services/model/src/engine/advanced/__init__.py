"""
Advanced Engine Modules.

고급 시나리오 처리 모듈:
- ReturnDetector: 상품 반납 감지 (시나리오 5)
- CrossZoneDetector: Zone 간 이동 감지 (시나리오 6)
- BaselineManager: Baseline 드리프트 보정 (시나리오 7)
- RapidPickupHandler: 연속 픽업 처리 (시나리오 8)
"""

from .return_detector import ReturnDetector, PickupEvent, ReturnResult
from .cross_zone_detector import CrossZoneDetector, MovementResult
from .baseline_manager import BaselineManager, ZoneBaseline
from .rapid_pickup_handler import RapidPickupHandler, BufferedWeightEvent, RapidPickupResult

__all__ = [
    # Return Detection
    "ReturnDetector",
    "PickupEvent",
    "ReturnResult",
    # Cross-Zone Detection
    "CrossZoneDetector",
    "MovementResult",
    # Baseline Management
    "BaselineManager",
    "ZoneBaseline",
    # Rapid Pickup
    "RapidPickupHandler",
    "BufferedWeightEvent",
    "RapidPickupResult",
]
