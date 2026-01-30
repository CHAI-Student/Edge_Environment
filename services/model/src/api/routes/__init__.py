"""
API Routes module.
"""

from .health import router as health_router
from .frame import router as frame_router
from .judge import router as judge_router
from .products import router as products_router

__all__ = [
    "health_router",
    "frame_router",
    "judge_router",
    "products_router",
]
