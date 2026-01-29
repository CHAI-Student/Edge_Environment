"""
FastAPI application manager for Model service.

This module provides:
- FastAPI application configuration
- Uvicorn server with graceful shutdown
- Lifespan management for AI components
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Callable

from fastapi import FastAPI
from uvicorn import Config as UvicornConfig, Server

from core.config import Settings
from core.logging_config import get_logger
from database.product_db import ProductDatabase
from engine import ProductDecisionEngine
from api.routes import router, init_routes
from api.node_client import NodeJSClient

logger = get_logger(__name__)


# ============================================================================
# Module-level instances (for route access)
# ============================================================================

product_db: Optional[ProductDatabase] = None
decision_engine: Optional[ProductDecisionEngine] = None
node_client: Optional[NodeJSClient] = None


def get_product_db() -> Optional[ProductDatabase]:
    """Get the product database instance."""
    return product_db


def get_decision_engine() -> Optional[ProductDecisionEngine]:
    """Get the decision engine instance."""
    return decision_engine


# ============================================================================
# YOLO Class Sync Utilities
# ============================================================================


def sync_yolo_classes_to_product_db(settings: Settings, db: ProductDatabase) -> int:
    """
    YOLO 모델의 클래스 이름을 ProductDatabase에 동기화.

    YOLO 모델에 정의된 클래스를 매핑 테이블에 등록합니다.
    기존 상품이 있으면 매핑만 업데이트하고, 없으면 새 상품을 생성합니다.

    Args:
        settings: Settings 인스턴스
        db: ProductDatabase 인스턴스

    Returns:
        동기화된 클래스 수
    """
    try:
        from vision import YOLOWrapper

        yolo = YOLOWrapper(model_path=settings.yolo_model_path)
        if not yolo.load():
            logger.warning("Failed to load YOLO model for class sync")
            return 0

        class_names = yolo.class_names
        if not class_names:
            logger.warning("YOLO model has no class names")
            return 0

        synced_count = 0
        for class_id, class_name in class_names.items():
            # hand (class_id=0)는 스킵
            if class_id == 0:
                continue

            # register_yolo_class 메서드 사용 (매핑 테이블 + 상품 등록)
            product_id = db.register_yolo_class(
                yolo_class_id=class_id,
                yolo_class_name=class_name,
                create_product=True,
            )

            if product_id is not None:
                synced_count += 1
                logger.debug(f"Synced YOLO class: id={class_id}, name={class_name}")

        logger.info(f"Synced {synced_count} YOLO classes to ProductDatabase")
        return synced_count

    except ImportError as e:
        logger.warning(f"YOLO not available for class sync: {e}")
        return 0
    except Exception as e:
        logger.error(f"YOLO class sync failed: {e}")
        return 0


def load_yolo_mapping_file(db: ProductDatabase) -> int:
    """
    YOLO-IF11 매핑 파일 로드.

    config/yolo_product_mapping.json 파일이 있으면 로드합니다.

    Args:
        db: ProductDatabase 인스턴스

    Returns:
        로드된 매핑 수
    """
    # 기본 매핑 파일 경로: src -> model -> services -> Edge_Environment -> config
    base_dir = Path(__file__).parent.parent.parent.parent.parent
    mapping_path = base_dir / "config" / "yolo_product_mapping.json"

    if not mapping_path.exists():
        logger.info(f"YOLO mapping file not found: {mapping_path}")
        return 0

    try:
        loaded_count = db.load_mapping_file(str(mapping_path))
        logger.info(f"Loaded {loaded_count} YOLO-IF11 mappings from {mapping_path}")
        return loaded_count
    except Exception as e:
        logger.error(f"Failed to load YOLO mapping file: {e}")
        return 0


# ============================================================================
# Lifespan Management
# ============================================================================


def create_lifespan(settings: Settings):
    """Create lifespan context manager with settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI 애플리케이션 수명 주기 관리."""
        global product_db, decision_engine, node_client

        logger.info("Model service starting (lightweight mode)...")

        # 1. ProductDatabase 초기화
        product_db = ProductDatabase()

        # 2. YOLO 모델 클래스 동기화
        yolo_synced = sync_yolo_classes_to_product_db(settings, product_db)

        # 3. 저장된 YOLO-IF11 매핑 파일 로드
        mapping_loaded = load_yolo_mapping_file(product_db)

        decision_engine = ProductDecisionEngine(product_db=product_db)
        node_client = NodeJSClient(base_url=settings.nodejs_url)

        # API 라우터 초기화
        init_routes(product_db, decision_engine)

        # Node.js 클라이언트 시작
        await node_client.start()

        logger.info(f"Model service ready on port {settings.port} (judgment-only)")
        logger.info(
            f"ProductDatabase: {product_db.product_count} products registered, "
            f"YOLO classes synced: {yolo_synced}, mappings loaded: {mapping_loaded}"
        )

        yield

        # 종료 처리
        logger.info("Model service shutting down...")

        if node_client:
            await node_client.stop()

        logger.info("Model service stopped")

    return lifespan


# ============================================================================
# FastAPI Application Factory
# ============================================================================


def create_app(settings: Settings) -> FastAPI:
    """
    Create and configure FastAPI application.

    Args:
        settings: Application settings

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Model Service",
        description="AI 상품 판단 서비스 - Vision + Weight Fusion",
        version="2.0.0",
        lifespan=create_lifespan(settings),
    )

    # 라우터 등록
    app.include_router(router)

    @app.get("/")
    async def root():
        """루트 엔드포인트."""
        return {
            "service": "model",
            "version": "2.0.0",
            "description": "AI 상품 판단 서비스",
        }

    return app


# ============================================================================
# Graceful Shutdown Server
# ============================================================================


class GracefulShutdownServer(Server):
    """Uvicorn server subclass that handles graceful shutdown."""

    def __init__(self, config: UvicornConfig, stop_event: asyncio.Event = None):
        super().__init__(config)
        self.stop_event = stop_event or asyncio.Event()

    async def shutdown(self, *args, **kwargs) -> None:
        """Handle server shutdown by setting the stop event."""
        self.stop_event.set()
        await super().shutdown(*args, **kwargs)


# ============================================================================
# Server Entry Point
# ============================================================================


async def serve_api(settings: Settings) -> None:
    """
    Start the FastAPI server with graceful shutdown support.

    Args:
        settings: Application settings
    """
    app = create_app(settings)

    uvicorn_config = UvicornConfig(
        app=app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        timeout_graceful_shutdown=settings.api.timeout_graceful_shutdown,
    )
    server = GracefulShutdownServer(uvicorn_config)

    logger.info(f"Starting API server on {settings.host}:{settings.port}")
    await server.serve()
