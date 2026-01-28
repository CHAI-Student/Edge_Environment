"""
Camera Driver Service

FastAPI 기반 6대 카메라 드라이버 서비스
포트: 8003

Event-Driven Architecture:
    IO Board SSE → Camera Driver (자체 버퍼링 & 저장)
                      ↓ (media_paths 전송)
                  Node.js (10초 타이머 + 누적 로직)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .api import router
from .api.streaming import router as streaming_router

logger = logging.getLogger(__name__)

# Global components for event-driven architecture
_sse_subscriber = None
_event_recording_manager = None


def _init_event_driven_components():
    """Initialize event-driven components (SSE subscriber + Event recording manager)"""
    global _sse_subscriber, _event_recording_manager

    from .core import IOBoardSSESubscriber, EventRecordingManager
    from .api.routes import get_manager, init_sse_components

    # Get camera manager
    manager = get_manager()

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
    from .api.routes import _manager
    if _manager:
        _manager.release_all()


app = FastAPI(
    title="Camera Driver Service",
    description="6-camera driver (Top 1 + Zone 5) with SSE-based event recording",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api", tags=["camera"])
app.include_router(streaming_router, prefix="/stream", tags=["streaming"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
