"""
API Routes module (v5.0).

AVI Trigger 방식만 사용하는 단순화된 API.
v5.0: products_router 제거 (ProductDatabase 제거)
"""

from .health import router as health_router
from .trigger import router as trigger_router
from .multi_zone import router as multi_zone_router

__all__ = [
    "health_router",
    "trigger_router",
    "multi_zone_router",
]
