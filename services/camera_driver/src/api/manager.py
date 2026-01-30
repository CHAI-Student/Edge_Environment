"""
FastAPI application manager for Camera Driver service.

This module provides:
- FastAPI application configuration
- Uvicorn server with graceful shutdown
- Event-driven component initialization
- Lifespan management for camera components
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from uvicorn import Config as UvicornConfig, Server

from core.config import settings
from core.logging_config import get_logger
from api import router
from api.streaming import router as streaming_router

logger = get_logger(__name__)

# Global components for event-driven architecture
_sse_subscriber = None
_event_recording_manager = None


# ============================================================================
# Event-Driven Components
# ============================================================================


async def _init_event_driven_components():
    """Initialize event-driven components (SSE subscriber + Event recording manager)"""
    global _sse_subscriber, _event_recording_manager

    from core import IOBoardSSESubscriber, EventRecordingManager
    from api.routes import get_manager, init_sse_components

    # Get camera manager
    manager = get_manager()

    # Auto-initialize all cameras on startup (별도 스레드에서 실행하여 블로킹 방지)
    logger.info("Auto-initializing cameras...")
    try:
        status = await asyncio.to_thread(manager.initialize_all)
        connected = sum(status.values())
        total = len(status)
        logger.info(f"Cameras initialized: {connected}/{total} connected")

        # Start streaming (별도 스레드에서 실행)
        await asyncio.to_thread(manager.start_streaming)
        logger.info("Camera streaming started")
    except Exception as e:
        logger.error(f"Camera initialization failed: {e}", exc_info=True)

    # Create SSE subscriber
    logger.info(f"Creating IOBoardSSESubscriber with io_board_url={settings.io_board_url}")
    try:
        _sse_subscriber = IOBoardSSESubscriber(
            io_board_url=settings.io_board_url,
        )
    except Exception as e:
        logger.error(f"Failed to create IOBoardSSESubscriber: {e}", exc_info=True)
        _sse_subscriber = None

    # Create event recording manager
    logger.info("Creating EventRecordingManager")
    try:
        _event_recording_manager = EventRecordingManager(
            camera_manager=manager,
            pre_buffer_seconds=settings.pre_buffer_seconds,
            post_buffer_seconds=settings.post_buffer_seconds,
            save_images=settings.save_images,
            save_videos=settings.save_videos,
            nodejs_callback_url=settings.nodejs_callback_url,
            model_service_url=settings.model_service_url,
            media_base_path=settings.media_base_path if settings.media_base_path else None,
        )
    except Exception as e:
        logger.error(f"Failed to create EventRecordingManager: {e}", exc_info=True)
        _event_recording_manager = None

    # Connect SSE events to recording manager (if both initialized)
    if _sse_subscriber and _event_recording_manager:
        _sse_subscriber.set_on_weight_change(_event_recording_manager.on_weight_change)
        _sse_subscriber.set_on_door_change(_event_recording_manager.on_door_change)
        logger.info("SSE subscriber callbacks linked to EventRecordingManager")
        print("[INIT] SSE callbacks linked to EventRecordingManager", flush=True)
    else:
        error_msg = f"SSE subscriber or EventRecordingManager not initialized; _sse_subscriber={_sse_subscriber}, _event_recording_manager={_event_recording_manager}"
        logger.warning(error_msg)
        print(f"[INIT] CRITICAL WARNING: {error_msg}", flush=True)

    # Register with routes module
    init_sse_components(_sse_subscriber, _event_recording_manager)

    logger.info("Event-driven components initialized")


async def _start_event_driven_services():
    """Start event-driven services"""
    global _sse_subscriber

    if _sse_subscriber:
        try:
            await _sse_subscriber.start()
            logger.info(f"SSE subscriber started: {settings.io_board_url}")
            print(f"[SSE] SSE subscriber successfully started on {settings.io_board_url}", flush=True)
        except Exception as e:
            logger.error(f"Failed to start SSE subscriber: {e}", exc_info=True)
            print(f"[SSE] ERROR: Failed to start SSE subscriber: {e}", flush=True)
            raise
    else:
        logger.warning("SSE subscriber is None, cannot start")
        print("[SSE] WARNING: SSE subscriber is None, cannot start", flush=True)


async def _stop_event_driven_services():
    """Stop event-driven services"""
    global _sse_subscriber, _event_recording_manager

    if _sse_subscriber:
        await _sse_subscriber.stop()
        logger.info("SSE subscriber stopped")

    if _event_recording_manager:
        await _event_recording_manager.close()
        logger.info("Event recording manager closed")


# ============================================================================
# Lifespan Management
# ============================================================================


def create_lifespan():
    """Create lifespan context manager."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI lifespan handler"""
        # Event-driven components readiness flag
        app.state.event_ready = False
        # Startup - 카메라 초기화를 백그라운드로 처리하여 서버가 먼저 시작되도록 함
        async def init_cameras_background():
            """백그라운드에서 카메라 초기화"""
            try:
                print("[STARTUP] Initializing cameras immediately...", flush=True)
                # 서버 시작과 동시에 카메라 초기화 시작 (대기 시간 최소화)
                await asyncio.sleep(0.1)  # 최소 대기
                print("[STARTUP] Initializing event-driven components...", flush=True)
                await _init_event_driven_components()
                print("[STARTUP] Starting event-driven services (SSE subscriber)...", flush=True)
                await _start_event_driven_services()
                print("[STARTUP] Event-driven services started successfully", flush=True)
                # Mark event-driven components as ready
                app.state.event_ready = True
            except Exception as e:
                logger.error(f"Failed to initialize cameras in background: {e}", exc_info=True)
                print(f"[STARTUP] CRITICAL ERROR: {e}", flush=True)
                import traceback
                print(traceback.format_exc(), flush=True)

        # 백그라운드 태스크로 카메라 초기화 시작
        init_task = asyncio.create_task(init_cameras_background())

        yield

        # Shutdown
        # 백그라운드 초기화가 아직 진행 중이면 취소
        if not init_task.done():
            init_task.cancel()
            try:
                await init_task
            except asyncio.CancelledError:
                pass

        await _stop_event_driven_services()

        # Cleanup camera manager
        from api.routes import _manager
        if _manager:
            _manager.release_all()

    return lifespan


# ============================================================================
# FastAPI Application Factory
# ============================================================================


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Camera Driver Service",
        description="6-camera driver (Top 1 + Zone 5) with SSE-based event recording",
        version="2.0.0",
        lifespan=create_lifespan(),
    )

    app.include_router(router, prefix="/api", tags=["camera"])
    app.include_router(streaming_router, prefix="/stream", tags=["streaming"])

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


async def serve_api() -> None:
    """
    Start the FastAPI server with graceful shutdown support.
    """
    app = create_app()

    uvicorn_config = UvicornConfig(
        app=app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )
    server = GracefulShutdownServer(uvicorn_config)

    logger.info(f"Starting API server on {settings.api_host}:{settings.api_port}")
    await server.serve()
