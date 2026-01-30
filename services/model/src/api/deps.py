"""
API Dependencies for Dependency Injection.

FastAPI Depends()를 위한 의존성 제공자.
전역 변수 대신 이 모듈을 통해 인스턴스에 접근합니다.
"""

import logging
from typing import Optional

from buffer import FrameBuffer
from vision import YOLOWrapper
from database.product_db import ProductDatabase
from engine import ProductDecisionEngine

logger = logging.getLogger(__name__)

# Module-level instances (initialized in lifespan)
_instances: dict = {}


def init_dependencies(
    frame_buffer: FrameBuffer,
    yolo: YOLOWrapper,
    engine: ProductDecisionEngine,
    product_db: ProductDatabase,
):
    """
    의존성 초기화 (lifespan에서 호출).

    Args:
        frame_buffer: FrameBuffer 인스턴스
        yolo: YOLOWrapper 인스턴스
        engine: ProductDecisionEngine 인스턴스
        product_db: ProductDatabase 인스턴스
    """
    _instances["buffer"] = frame_buffer
    _instances["yolo"] = yolo
    _instances["engine"] = engine
    _instances["db"] = product_db

    logger.info(
        f"Dependencies initialized: "
        f"buffer={frame_buffer is not None}, "
        f"yolo={yolo is not None}, "
        f"engine={engine is not None}, "
        f"db={product_db is not None}"
    )


def cleanup_dependencies():
    """의존성 정리 (shutdown 시 호출)."""
    if "buffer" in _instances:
        _instances["buffer"].clear_all()

    _instances.clear()
    logger.info("Dependencies cleaned up")


# ============================================================================
# Dependency Getters (for FastAPI Depends)
# ============================================================================


def get_frame_buffer() -> FrameBuffer:
    """FrameBuffer 인스턴스 반환."""
    buffer = _instances.get("buffer")
    if buffer is None:
        raise RuntimeError("FrameBuffer not initialized. Call init_dependencies() first.")
    return buffer


def get_yolo() -> YOLOWrapper:
    """YOLOWrapper 인스턴스 반환."""
    yolo = _instances.get("yolo")
    if yolo is None:
        raise RuntimeError("YOLOWrapper not initialized. Call init_dependencies() first.")
    return yolo


def get_decision_engine() -> ProductDecisionEngine:
    """ProductDecisionEngine 인스턴스 반환."""
    engine = _instances.get("engine")
    if engine is None:
        raise RuntimeError("ProductDecisionEngine not initialized. Call init_dependencies() first.")
    return engine


def get_product_db() -> ProductDatabase:
    """ProductDatabase 인스턴스 반환."""
    db = _instances.get("db")
    if db is None:
        raise RuntimeError("ProductDatabase not initialized. Call init_dependencies() first.")
    return db


# ============================================================================
# Optional Getters (may return None)
# ============================================================================


def get_frame_buffer_optional() -> Optional[FrameBuffer]:
    """FrameBuffer 인스턴스 반환 (None 허용)."""
    return _instances.get("buffer")


def get_yolo_optional() -> Optional[YOLOWrapper]:
    """YOLOWrapper 인스턴스 반환 (None 허용)."""
    return _instances.get("yolo")


def get_decision_engine_optional() -> Optional[ProductDecisionEngine]:
    """ProductDecisionEngine 인스턴스 반환 (None 허용)."""
    return _instances.get("engine")


def get_product_db_optional() -> Optional[ProductDatabase]:
    """ProductDatabase 인스턴스 반환 (None 허용)."""
    return _instances.get("db")


# ============================================================================
# Status Check
# ============================================================================


def is_initialized() -> bool:
    """의존성 초기화 상태 확인."""
    required_keys = ["buffer", "yolo", "engine", "db"]
    return all(key in _instances for key in required_keys)


def get_status() -> dict:
    """의존성 상태 반환."""
    return {
        "initialized": is_initialized(),
        "buffer": _instances.get("buffer") is not None,
        "yolo": _instances.get("yolo") is not None,
        "engine": _instances.get("engine") is not None,
        "db": _instances.get("db") is not None,
    }
