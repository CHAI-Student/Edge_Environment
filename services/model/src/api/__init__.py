"""
API module for Model service.

REST API 엔드포인트.

엔드포인트:
- GET /api/health: 헬스 체크
- POST /api/frame: 이미지 프레임 수신
- POST /api/judge: 상품 판단
- GET /api/products: 상품 목록
"""

from .routes import (
    health_router,
    frame_router,
    judge_router,
    products_router,
)
from .deps import (
    init_dependencies,
    cleanup_dependencies,
    get_frame_buffer,
    get_yolo,
    get_decision_engine,
    get_product_db,
)
from .manager import create_app, serve_api

__all__ = [
    # Routers
    "health_router",
    "frame_router",
    "judge_router",
    "products_router",
    # Dependency Injection
    "init_dependencies",
    "cleanup_dependencies",
    "get_frame_buffer",
    "get_yolo",
    "get_decision_engine",
    "get_product_db",
    # Application
    "create_app",
    "serve_api",
]
