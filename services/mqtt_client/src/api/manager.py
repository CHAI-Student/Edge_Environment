"""
FastAPI application manager for MQTT Client service.

This module provides:
- FastAPI application configuration
- Uvicorn server with graceful shutdown
- MQTT client lifecycle management
- Health check endpoints
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import aiomqtt
from fastapi import FastAPI
from uvicorn import Config as UvicornConfig, Server

from core.config import settings
from core.logging_config import get_logger
from core import core

logger = get_logger(__name__)

# Global MQTT client task reference
mqtt_client_task: Optional[asyncio.Task] = None


# ============================================================================
# MQTT Client Runner
# ============================================================================


async def run_mqtt_client():
    """MQTT 클라이언트 실행 (지수 백오프 재연결)"""
    kwargs = {
        "hostname": settings.mqtt_broker_host,
        "port": settings.mqtt_broker_port,
    }

    if settings.mqtt_client_username:
        kwargs["username"] = settings.mqtt_client_username
    if settings.mqtt_client_password:
        kwargs["password"] = settings.mqtt_client_password

    # 재연결 설정
    base_delay = 5  # 초기 대기 시간 (초)
    max_delay = 300  # 최대 대기 시간 (5분)
    retry_count = 0

    while True:
        try:
            async with aiomqtt.Client(**kwargs) as client:
                logger.info(
                    f"MQTT connected to {settings.mqtt_broker_host}:{settings.mqtt_broker_port}"
                )
                retry_count = 0  # 연결 성공 시 리셋
                await core.run(client)
        except aiomqtt.MqttError as e:
            retry_count += 1
            delay = min(base_delay * (2 ** min(retry_count - 1, 6)), max_delay)
            logger.warning(
                f"MQTT connection error: {e}. "
                f"Reconnecting in {delay}s (attempt {retry_count})..."
            )
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info("MQTT client task cancelled")
            raise
        except Exception as e:
            retry_count += 1
            delay = min(base_delay * (2 ** min(retry_count - 1, 6)), max_delay)
            logger.warning(
                f"MQTT error: {e}. "
                f"Reconnecting in {delay}s (attempt {retry_count})..."
            )
            await asyncio.sleep(delay)


# ============================================================================
# Lifespan Management
# ============================================================================


def create_lifespan():
    """Create lifespan context manager."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI lifespan handler"""
        global mqtt_client_task
        mqtt_client_task = asyncio.create_task(run_mqtt_client())
        yield
        if mqtt_client_task:
            mqtt_client_task.cancel()
            try:
                await mqtt_client_task
            except asyncio.CancelledError:
                pass

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
        title="MQTT Client Service",
        description="MQTT Client for CHAI Interface (IF01-04)",
        version="2.0.0",
        lifespan=create_lifespan(),
    )

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "service": "mqtt_client",
            "mqtt_broker": f"{settings.mqtt_broker_host}:{settings.mqtt_broker_port}",
            "mqtt_connected": mqtt_client_task is not None and not mqtt_client_task.done(),
        }

    @app.get("/status")
    async def get_status():
        """Get MQTT client status"""
        return {
            "division_idx": settings.division_idx,
            "device_idx": settings.device_idx,
            "mqtt_broker_host": settings.mqtt_broker_host,
            "mqtt_broker_port": settings.mqtt_broker_port,
            "router_handlers": list(core.router.handlers.keys()),
            "scheduler_schedules": len(core.scheduler.schedules),
            "router_pending_tasks": core.router.remaining_tasks(),
            "scheduler_pending_tasks": core.scheduler.remaining_tasks(),
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
