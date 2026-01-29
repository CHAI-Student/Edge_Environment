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


def _init_event_driven_components():
    """Initialize event-driven components (SSE subscriber + Event recording manager)"""
    global _sse_subscriber, _event_recording_manager

    from core import IOBoardSSESubscriber, EventRecordingManager
    from api.routes import get_manager, init_sse_components

    # Get camera manager and auto-initialize cameras
    manager = get_manager()

    # Auto-initialize all cameras on startup
    logger.info("Auto-initializing cameras...")
    status = manager.initialize_all()
    connected = sum(status.values())
    total = len(status)
    logger.info(f"Cameras initialized: {connected}/{total} connected")

    # Start streaming
    manager.start_streaming()
    logger.info("Camera streaming started")

    # Create SSE subscriber
    _sse_subscriber = IOBoardSSESubscriber(
        io_board_url=settings.io_board_url,
    )

    # Create event recording manager
    _event_recording_manager = EventRecordingManager(
        camera_manager=manager,
        pre_buffer_seconds=settings.pre_buffer_seconds,
        post_buffer_seconds=settings.post_buffer_seconds,
        save_images=settings.save_images,
        save_videos=settings.save_videos,
        nodejs_callback_url=settings.nodejs_callback_url,
        media_base_path=settings.media_base_path if settings.media_base_path else None,
    )

    # Connect SSE events to recording manager
    _sse_subscriber.set_on_weight_change(_event_recording_manager.on_weight_change)
    _sse_subscriber.set_on_door_change(_event_recording_manager.on_door_change)

    # Register with routes module
    init_sse_components(_sse_subscriber, _event_recording_manager)

    logger.info("Event-driven components initialized")


async def _start_event_driven_services():
    """Start event-driven services"""
    global _sse_subscriber

    if _sse_subscriber:
        await _sse_subscriber.start()
        logger.info(f"SSE subscriber started: {settings.io_board_url}")


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
        # Startup
        _init_event_driven_components()
        await _start_event_driven_services()

        yield

        # Shutdown
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
