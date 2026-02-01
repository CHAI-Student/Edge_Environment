"""
Health Check API Routes (v4.0).

GET /api/health - 서비스 헬스 체크
"""

import os
import time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from core.config import config
from api.deps import is_initialized, get_status

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    """헬스 체크 응답."""

    model: str  # "HEALTHY" | "UNHEALTHY"
    status: str = "ok"
    yolo_loaded: bool = False
    session_store_ready: bool = False
    timestamp: float = 0.0


class DetailedHealthResponse(BaseModel):
    """상세 헬스 체크 응답."""

    service: str = "model"
    version: str = "4.0.0"
    status: str = "ok"
    dependencies: dict = {}
    config: dict = {}
    timestamp: float = 0.0


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    기본 헬스 체크.

    Returns:
        HealthResponse: 헬스 상태
    """
    model_path = config.yolo_model_path

    # 상대 경로인 경우 절대 경로로 변환
    if not os.path.isabs(model_path):
        # services/model/src/api/routes -> services/model
        base_dir = Path(__file__).parent.parent.parent.parent
        # Edge_Environment 기준으로 해석
        project_root = base_dir.parent
        model_path = str(project_root / model_path)

    model_exists = os.path.exists(model_path)
    deps_status = get_status()

    return HealthResponse(
        model="HEALTHY" if model_exists else "UNHEALTHY",
        status="ok" if is_initialized() else "initializing",
        yolo_loaded=deps_status.get("yolo", False),
        session_store_ready=deps_status.get("session_store", False),
        timestamp=time.time(),
    )


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check():
    """
    상세 헬스 체크.

    Returns:
        DetailedHealthResponse: 상세 헬스 상태
    """
    deps_status = get_status()

    return DetailedHealthResponse(
        service="model",
        version="4.0.0",
        status="ok" if is_initialized() else "initializing",
        dependencies=deps_status,
        config={
            "host": config.host,
            "port": config.port,
            "yolo_model_path": config.yolo_model_path,
        },
        timestamp=time.time(),
    )
