"""
FastAPI application manager for Model service (v4.2).

This module provides:
- FastAPI application configuration
- Uvicorn server with graceful shutdown
- Lifespan management for AI components
- Background cleanup tasks for TTL expiration

v4.2 변경사항:
- TTL 자동 정리 백그라운드 태스크 추가
- YAML cleanup 자동화 (서비스 종료 시)
- ServiceContainer 통합

v4.1 변경사항:
- DoorSessionStore 추가

v4.0 변경사항:
- FrameBuffer 제거
- SessionStore 추가
- Frame Buffer API 제거, AVI Trigger만 사용
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from uvicorn import Config as UvicornConfig, Server

from core.config import Settings
from core.logging_config import get_logger
from database.product_db import ProductDatabase
from engine import ProductDecisionEngine
from vision import YOLOWrapper
from session import SessionStore, DoorSessionStore
from api.deps import init_dependencies, cleanup_dependencies
from api.routes import (
    health_router,
    products_router,
    trigger_router,
    multi_zone_router,
)

logger = get_logger(__name__)


# ============================================================================
# Background Cleanup Tasks
# ============================================================================


async def session_cleanup_task(
    session_store: SessionStore,
    interval_seconds: float = 60.0,
    stop_event: asyncio.Event = None,
) -> None:
    """
    세션 TTL 정리 백그라운드 태스크.

    지정된 간격으로 만료된 세션을 자동 정리합니다.

    Args:
        session_store: SessionStore 인스턴스
        interval_seconds: 정리 주기 (초)
        stop_event: 태스크 종료 신호
    """
    logger.info(f"Session cleanup task started (interval={interval_seconds}s)")

    while True:
        try:
            # stop_event가 설정되면 종료
            if stop_event is not None and stop_event.is_set():
                logger.info("Session cleanup task stopping (stop event set)")
                break

            # 만료된 세션 정리
            cleaned = session_store.cleanup_expired()
            if cleaned > 0:
                logger.info(f"Session cleanup: removed {cleaned} expired sessions")

            # 다음 주기까지 대기
            await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            logger.info("Session cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Session cleanup task error: {e}", exc_info=True)
            await asyncio.sleep(interval_seconds)

    logger.info("Session cleanup task stopped")


# ============================================================================
# YOLO Class Sync Utilities
# ============================================================================


def sync_yolo_classes_to_product_db(yolo: YOLOWrapper, db: ProductDatabase) -> int:
    """
    YOLO 모델의 클래스 이름을 ProductDatabase에 동기화.

    Args:
        yolo: YOLOWrapper 인스턴스
        db: ProductDatabase 인스턴스

    Returns:
        동기화된 클래스 수
    """
    if not yolo.is_loaded:
        logger.warning("YOLO model not loaded for class sync")
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

        # register_yolo_class 메서드 사용
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


def load_yolo_mapping_file(db: ProductDatabase) -> int:
    """
    YOLO-IF11 매핑 파일 로드.

    Args:
        db: ProductDatabase 인스턴스

    Returns:
        로드된 매핑 수
    """
    # 기본 매핑 파일 경로: src/api -> model -> services -> Edge_Environment -> config
    base_dir = Path(__file__).parent.parent.parent.parent
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
        logger.info("Model service starting...")

        # 1. SessionStore 초기화
        session_store = SessionStore(
            ttl_seconds=settings.buffer.ttl_seconds,
            max_sessions=settings.buffer.max_sessions,
        )

        # 2. ProductDatabase 초기화
        product_db = ProductDatabase()

        # 3. YOLO 모델 로드
        yolo = YOLOWrapper(model_path=settings.yolo_model_path)
        yolo_loaded = yolo.load()

        # 4. YOLO 모델 클래스 동기화
        yolo_synced = 0
        if yolo_loaded:
            yolo_synced = sync_yolo_classes_to_product_db(yolo, product_db)

        # 5. 저장된 YOLO-IF11 매핑 파일 로드
        mapping_loaded = load_yolo_mapping_file(product_db)

        # 6. ProductDecisionEngine 초기화
        decision_engine = ProductDecisionEngine(product_db=product_db)

        # 7. DoorSessionStore 초기화 (v4.1)
        door_session_store = None
        if settings.door_session.enabled:
            door_session_store = DoorSessionStore(
                yaml_dir=settings.door_session.yaml_dir,
                session_timeout=settings.door_session.session_timeout_seconds,
                weight_tolerance=settings.door_session.weight_tolerance_grams,
                max_duration=settings.door_session.max_duration_seconds,
                get_product_weight=lambda pid: product_db.get_weight(pid),
            )
            # 활성 세션 복구
            recovered = door_session_store.recover_active_sessions()
            logger.info(f"DoorSessionStore: recovered {recovered} active sessions")

        # 8. 의존성 주입 초기화
        init_dependencies(
            session_store=session_store,
            yolo=yolo,
            engine=decision_engine,
            product_db=product_db,
            door_session_store=door_session_store,
        )

        # 9. 백그라운드 정리 태스크 시작 (v4.2)
        cleanup_stop_event = asyncio.Event()
        cleanup_interval = settings.buffer.cleanup_interval_seconds
        cleanup_task = asyncio.create_task(
            session_cleanup_task(
                session_store=session_store,
                interval_seconds=cleanup_interval,
                stop_event=cleanup_stop_event,
            )
        )

        logger.info(f"Model service ready on port {settings.port}")
        logger.info(
            f"ProductDatabase: {product_db.product_count} products, "
            f"YOLO classes synced: {yolo_synced}, mappings loaded: {mapping_loaded}"
        )
        logger.info(
            f"SessionStore: ttl={settings.buffer.ttl_seconds}s, "
            f"max_sessions={settings.buffer.max_sessions}, "
            f"cleanup_interval={cleanup_interval}s"
        )
        if settings.door_session.enabled:
            logger.info(
                f"DoorSessionStore: timeout={settings.door_session.session_timeout_seconds}s, "
                f"tolerance={settings.door_session.weight_tolerance_grams}g, "
                f"max_duration={settings.door_session.max_duration_seconds}s"
            )

        yield

        # 종료 처리
        logger.info("Model service shutting down...")

        # 10. 백그라운드 태스크 종료 (v4.2)
        cleanup_stop_event.set()
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

        # 11. YAML 오래된 세션 정리 (v4.2)
        if door_session_store is not None:
            try:
                days_to_keep = settings.door_session.yaml_retention_days
                deleted = door_session_store._persistence.cleanup_old_sessions(
                    days_to_keep=days_to_keep
                )
                if deleted > 0:
                    logger.info(
                        f"YAML cleanup: removed {deleted} old session files "
                        f"(older than {days_to_keep} days)"
                    )
            except Exception as e:
                logger.error(f"YAML cleanup failed: {e}")

        cleanup_dependencies()
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
        description="AI 상품 판단 서비스 - AVI Trigger + Vision + Weight Fusion (v4.0)",
        version="4.0.0",
        lifespan=create_lifespan(settings),
    )

    # 라우터 등록
    app.include_router(health_router)
    app.include_router(products_router)
    app.include_router(trigger_router)
    app.include_router(multi_zone_router)

    @app.get("/")
    async def root():
        """루트 엔드포인트."""
        return {
            "service": "model",
            "version": "4.0.0",
            "description": "AI 상품 판단 서비스 (AVI Trigger API)",
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
