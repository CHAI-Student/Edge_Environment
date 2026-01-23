"""
Camera Driver Service

FastAPI 기반 6대 카메라 드라이버 서비스
포트: 8003
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .api import router
from .api.streaming import router as streaming_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler"""
    yield
    # Cleanup on shutdown
    from .api.routes import _manager

    if _manager:
        _manager.release_all()


app = FastAPI(
    title="Camera Driver Service",
    description="6-camera driver (Top 1 + Zone 5) with streaming support",
    version="1.0.0",
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
