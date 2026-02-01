"""
API Routes module (v4.0).

AVI Trigger 방식만 사용하는 단순화된 API.
"""

from .health import router as health_router
from .products import router as products_router
from .trigger import router as trigger_router
from .multi_zone import router as multi_zone_router

__all__ = [
    "health_router",
    "products_router",
    "trigger_router",
    "multi_zone_router",
]
