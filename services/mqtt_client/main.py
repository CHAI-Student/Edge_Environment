"""
MQTT Client Service

FastAPI 래퍼를 통한 MQTT 클라이언트 서비스
포트: 8006
"""

import asyncio
from contextlib import asynccontextmanager

import aiomqtt
from fastapi import FastAPI

from .config import settings
from .core import core

# Import protocols to register handlers
from .protocol import IF01, IF02, IF03, IF04


mqtt_client_task: asyncio.Task | None = None


async def run_mqtt_client():
    """MQTT 클라이언트 실행"""
    kwargs = {
        "hostname": settings.mqtt_broker_host,
        "port": settings.mqtt_broker_port,
    }

    if settings.mqtt_client_username:
        kwargs["username"] = settings.mqtt_client_username
    if settings.mqtt_client_password:
        kwargs["password"] = settings.mqtt_client_password

    while True:
        try:
            async with aiomqtt.Client(**kwargs) as client:
                print(
                    f"MQTT connected to {settings.mqtt_broker_host}:{settings.mqtt_broker_port}"
                )
                await core.run(client)
        except aiomqtt.MqttError as e:
            print(f"MQTT connection error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"MQTT error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)


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


app = FastAPI(
    title="MQTT Client Service",
    description="MQTT Client for CHAI Interface (IF01-04)",
    version="1.0.0",
    lifespan=lifespan,
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
