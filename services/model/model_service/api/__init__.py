"""
API module for Model service (v5.0).

REST API 엔드포인트.

엔드포인트:
- GET /api/health: 헬스 체크
- POST /trigger: Camera에서 녹화 완료 시 호출
- POST /api/judge/multi-zone: Node.js 폴링용

v5.0: products_router, get_product_db 제거 (ProductDatabase 제거)
"""

from .routes import (
    health_router,
    trigger_router,
    multi_zone_router,
)
from .deps import (
    init_dependencies,
    cleanup_dependencies,
    get_session_store,
    get_yolo,
    get_decision_engine,
    get_video_processor,
)
from .manager import create_app, serve_api

__all__ = [
    # Routers
    "health_router",
    "trigger_router",
    "multi_zone_router",
    # Dependency Injection
    "init_dependencies",
    "cleanup_dependencies",
    "get_session_store",
    "get_yolo",
    "get_decision_engine",
    "get_video_processor",
    # Application
    "create_app",
    "serve_api",
]
