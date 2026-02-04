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
from engine import ProductDecisionEngine
from vision import YOLOWrapper
from session import SessionStore, DoorSessionStore
from session.active_product_store import ActiveProductStore
from api.deps import init_dependencies, cleanup_dependencies
from api.routes import (
    health_router,
    trigger_router,
    multi_zone_router,
)

logger = get_logger(__name__)


# ============================================================================
# Background Cleanup Tasks
# ============================================================================


async def session_cleanup_task(
    session_store: SessionStore,
    door_session_store: Optional[DoorSessionStore] = None,
    interval_seconds: float = 60.0,
    stop_event: asyncio.Event = None,
) -> None:
    """
    세션 TTL 정리 백그라운드 태스크 (v4.5).

    지정된 간격으로 만료된 세션을 자동 정리합니다.

    v4.5 변경사항:
    - PendingTriggerStore cleanup 제거
    - DoorSessionStore cleanup 추가 (GlobalSession max_duration 체크)
    - Sleep을 5초 단위로 분할 (빠른 shutdown 지원)

    Args:
        session_store: SessionStore 인스턴스
        door_session_store: DoorSessionStore 인스턴스 (v4.5)
        interval_seconds: 정리 주기 (초)
        stop_event: 태스크 종료 신호
    """
    logger.info(f"Session cleanup task started (interval={interval_seconds}s)")

    # v4.5: 빠른 shutdown을 위해 5초 단위로 sleep 분할
    sleep_chunk = 5.0
    elapsed_since_cleanup = 0.0

    while True:
        try:
            # stop_event가 설정되면 종료
            if stop_event is not None and stop_event.is_set():
                logger.info("Session cleanup task stopping (stop event set)")
                break

            # v4.5: 분할된 sleep
            await asyncio.sleep(sleep_chunk)
            elapsed_since_cleanup += sleep_chunk

            # stop_event 재확인 (sleep 후)
            if stop_event is not None and stop_event.is_set():
                logger.info("Session cleanup task stopping (stop event set after sleep)")
                break

            # 지정된 간격이 지났으면 cleanup 수행
            if elapsed_since_cleanup >= interval_seconds:
                elapsed_since_cleanup = 0.0

                # 만료된 세션 정리
                cleaned = session_store.cleanup_expired()
                if cleaned > 0:
                    logger.info(f"Session cleanup: removed {cleaned} expired sessions")

                # v4.5: DoorSessionStore 타임아웃 정리 (GlobalSession 포함)
                if door_session_store is not None:
                    door_cleaned = door_session_store.cleanup_timed_out_sessions()
                    if door_cleaned > 0:
                        logger.info(f"Door session cleanup: removed {door_cleaned} timed out sessions")

        except asyncio.CancelledError:
            logger.info("Session cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Session cleanup task error: {e}", exc_info=True)
            # 에러 발생 시에도 분할된 sleep 유지
            elapsed_since_cleanup = 0.0

    logger.info("Session cleanup task stopped")


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

        # 2. YOLO 모델 로드
        yolo = YOLOWrapper(model_path=settings.yolo_model_path)
        yolo_loaded = yolo.load()

        # 3. ActiveProductStore 초기화 (v4.4)
        # yolo_product_mapping.json에서 yolo_class_name → yolo_class_id 매핑 로드
        yolo_name_to_id = {}
        for class_id, class_name in (yolo.class_names or {}).items():
            if class_id > 0:  # hand (0) 제외
                yolo_name_to_id[class_name] = class_id

        active_product_store = ActiveProductStore(yolo_name_to_id=yolo_name_to_id)

        # 매핑 파일에서 추가 로드
        base_dir = Path(__file__).parent.parent.parent.parent
        mapping_path = base_dir / "config" / "yolo_product_mapping.json"
        if mapping_path.exists():
            import json
            try:
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    mapping_data = json.load(f)
                loaded = active_product_store.load_yolo_mapping(mapping_data)
                logger.info(f"ActiveProductStore: loaded {loaded} YOLO mappings")
            except Exception as e:
                logger.error(f"Failed to load YOLO mapping for ActiveProductStore: {e}")

        # 4. ProductDecisionEngine 초기화 (v5.0: ActiveProductStore 사용)
        decision_engine = ProductDecisionEngine(product_db=active_product_store)

        # 5. DoorSessionStore 초기화 (v5.0: ActiveProductStore에서 weight 조회)
        door_session_store = None
        if settings.door_session.enabled:
            door_session_store = DoorSessionStore(
                yaml_dir=settings.door_session.yaml_dir,
                session_timeout=settings.door_session.session_timeout_seconds,
                weight_tolerance=settings.door_session.weight_tolerance_grams,
                max_duration=settings.door_session.max_duration_seconds,
                get_product_weight=lambda pid: active_product_store.get_product_weight(pid),
            )
            # 활성 세션 복구
            recovered = door_session_store.recover_active_sessions()
            logger.info(f"DoorSessionStore: recovered {recovered} active sessions")

        # 6. 의존성 주입 초기화 (v5.0: product_db 제거)
        init_dependencies(
            session_store=session_store,
            yolo=yolo,
            engine=decision_engine,
            door_session_store=door_session_store,
            active_product_store=active_product_store,
        )

        # 7. 백그라운드 정리 태스크 시작
        cleanup_stop_event = asyncio.Event()
        cleanup_interval = settings.buffer.cleanup_interval_seconds
        cleanup_task = asyncio.create_task(
            session_cleanup_task(
                session_store=session_store,
                door_session_store=door_session_store,
                interval_seconds=cleanup_interval,
                stop_event=cleanup_stop_event,
            )
        )

        logger.info(f"Model service ready on port {settings.port}")
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

        # 11. 백그라운드 태스크 종료 (v4.5)
        cleanup_stop_event.set()
        cleanup_task.cancel()
        active_product_store.clear()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

        # 12. YAML 오래된 세션 정리 (v4.5)
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

            # v4.8: DoorSessionStore 스레드풀 정리 (백그라운드 YAML 저장 완료 대기)
            door_session_store.shutdown()

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
