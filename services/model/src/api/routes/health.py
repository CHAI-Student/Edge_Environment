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
        # services/model/src/api/routes/health.py
        # -> parent x5 = services/model
        # -> parent x6 = services
        # -> parent x7 = Edge_Environment
        routes_dir = Path(__file__).parent  # routes
        api_dir = routes_dir.parent  # api
        src_dir = api_dir.parent  # src
        model_dir = src_dir.parent  # model
        services_dir = model_dir.parent  # services
        project_root = services_dir.parent  # Edge_Environment
        model_path = str(project_root / model_path)

    model_exists = os.path.exists(model_path)
    deps_status = get_status()

    # yolo_loaded: 실제 모델 로드 상태 확인
    yolo_instance = deps_status.get("yolo_instance")
    yolo_loaded = yolo_instance.is_loaded if yolo_instance else False

    return HealthResponse(
        model="HEALTHY" if model_exists else "UNHEALTHY",
        status="ok" if is_initialized() else "initializing",
        yolo_loaded=yolo_loaded,
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

    # yolo_instance는 객체라서 JSON 직렬화 불가, 제외
    serializable_deps = {
        k: v for k, v in deps_status.items()
        if k != "yolo_instance"
    }

    return DetailedHealthResponse(
        service="model",
        version="4.0.0",
        status="ok" if is_initialized() else "initializing",
        dependencies=serializable_deps,
        config={
            "host": config.host,
            "port": config.port,
            "yolo_model_path": config.yolo_model_path,
        },
        timestamp=time.time(),
    )
