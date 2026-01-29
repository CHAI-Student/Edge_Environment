"""
MQTT Client Service

FastAPI 래퍼를 통한 MQTT 클라이언트 서비스
포트: 8006

실행 방법:
    python main.py
"""

import asyncio
import sys
from contextlib import asynccontextmanager

import aiomqtt
from fastapi import FastAPI
from uvicorn import Config as UvicornConfig, Server

from core.config import settings
from core.logging_config import get_logger, setup_logging
from core import core

# =============================================================================
# Protocol Imports (Handler Registration)
# =============================================================================
# NOTE: Node.js 서버가 IF01, IF02, IF03를 담당합니다.
#       Python mqtt_client는 IF04 및 향후 추가되는 인터페이스만 담당합니다.
#
# Node.js 담당 (server/routes/Mqtt/):
#   - IF01 (Reboot): RebootMqtt.js
#   - IF02 (Health Check): HealthMqtt.js
#   - IF03 (Manual Door): ManualDoor.js
#
# Python 담당:
#   - IF04 (Collect Door): 수거함 도어 제어
#   - IF05+ (향후 추가)
# =============================================================================
# from protocol import IF01  # Node.js 담당 (RebootMqtt.js)
# from protocol import IF02  # Node.js 담당 (HealthMqtt.js)
# from protocol import IF03  # Node.js 담당 (ManualDoor.js)
from protocol import IF04  # Python 담당 - Collect Door


mqtt_client_task: asyncio.Task | None = None


async def run_mqtt_client(logger):
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
    max_retries = 20  # 최대 재시도 횟수 (이후 계속 max_delay로 시도)

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


def create_lifespan(logger):
    """Create lifespan context manager with logger."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI lifespan handler"""
        global mqtt_client_task
        mqtt_client_task = asyncio.create_task(run_mqtt_client(logger))
        yield
        if mqtt_client_task:
            mqtt_client_task.cancel()
            try:
                await mqtt_client_task
            except asyncio.CancelledError:
                pass

    return lifespan


class GracefulShutdownServer(Server):
    """Uvicorn server subclass that handles graceful shutdown."""

    def __init__(self, config: UvicornConfig, stop_event: asyncio.Event = None):
        super().__init__(config)
        self.stop_event = stop_event or asyncio.Event()

    async def shutdown(self, *args, **kwargs) -> None:
        """Handle server shutdown by setting the stop event."""
        self.stop_event.set()
        await super().shutdown(*args, **kwargs)


async def serve_api(logger):
    """FastAPI 서버 실행 (GracefulShutdownServer 패턴)."""
    app = FastAPI(
        title="MQTT Client Service",
        description="MQTT Client for CHAI Interface (IF01-04)",
        version="2.0.0",
        lifespan=create_lifespan(logger),
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

    uvicorn_config = UvicornConfig(
        app=app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )
    server = GracefulShutdownServer(uvicorn_config)
    await server.serve()


async def async_main(logger):
    """비동기 메인 진입점."""
    logger.info(f"Starting MQTT Client on {settings.api_host}:{settings.api_port}")
    await serve_api(logger)


def run():
    """Run the MQTT Client service (entry point for PM2)."""
    # Setup logging
    setup_logging(settings.log_level.upper())
    logger = get_logger(__name__)

    try:
        asyncio.run(async_main(logger))
    except KeyboardInterrupt:
        logger.info("MQTT Client stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"MQTT Client failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
