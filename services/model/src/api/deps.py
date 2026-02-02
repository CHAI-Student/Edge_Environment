"""
API Dependencies for Dependency Injection (v4.0).

FastAPI Depends()를 위한 의존성 제공자.
전역 변수 대신 이 모듈을 통해 인스턴스에 접근합니다.

v4.0 변경사항:
- FrameBuffer 제거
- SessionStore 추가
"""

import logging
from typing import Optional

from session import SessionStore, DoorSessionStore
from vision import YOLOWrapper
from database.product_db import ProductDatabase
from engine import ProductDecisionEngine
from video import VideoProcessor

logger = logging.getLogger(__name__)

# Module-level instances (initialized in lifespan)
_instances: dict = {}


def init_dependencies(
    session_store: SessionStore,
    yolo: YOLOWrapper,
    engine: ProductDecisionEngine,
    product_db: ProductDatabase,
    video_processor: Optional[VideoProcessor] = None,
    door_session_store: Optional[DoorSessionStore] = None,
):
    """
    의존성 초기화 (lifespan에서 호출).

    Args:
        session_store: SessionStore 인스턴스
        yolo: YOLOWrapper 인스턴스
        engine: ProductDecisionEngine 인스턴스
        product_db: ProductDatabase 인스턴스
        video_processor: VideoProcessor 인스턴스 (선택)
        door_session_store: DoorSessionStore 인스턴스 (선택, v4.1)
    """
    _instances["session_store"] = session_store
    _instances["yolo"] = yolo
    _instances["engine"] = engine
    _instances["db"] = product_db
    _instances["door_session_store"] = door_session_store

    # VideoProcessor는 yolo를 공유
    if video_processor is not None:
        _instances["video_processor"] = video_processor
    else:
        _instances["video_processor"] = VideoProcessor(yolo=yolo)

    logger.info(
        f"Dependencies initialized: "
        f"session_store={session_store is not None}, "
        f"yolo={yolo is not None}, "
        f"engine={engine is not None}, "
        f"db={product_db is not None}, "
        f"video_processor={_instances.get('video_processor') is not None}, "
        f"door_session_store={door_session_store is not None}"
    )


def cleanup_dependencies():
    """의존성 정리 (shutdown 시 호출)."""
    if "session_store" in _instances:
        _instances["session_store"].clear_all()

    if "door_session_store" in _instances and _instances["door_session_store"] is not None:
        _instances["door_session_store"].clear_all()

    _instances.clear()
    logger.info("Dependencies cleaned up")


# ============================================================================
# Dependency Getters (for FastAPI Depends)
# ============================================================================


def get_session_store() -> SessionStore:
    """SessionStore 인스턴스 반환."""
    store = _instances.get("session_store")
    if store is None:
        raise RuntimeError("SessionStore not initialized. Call init_dependencies() first.")
    return store


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


def get_video_processor() -> VideoProcessor:
    """VideoProcessor 인스턴스 반환."""
    processor = _instances.get("video_processor")
    if processor is None:
        raise RuntimeError("VideoProcessor not initialized. Call init_dependencies() first.")
    return processor


def get_door_session_store() -> DoorSessionStore:
    """DoorSessionStore 인스턴스 반환."""
    store = _instances.get("door_session_store")
    if store is None:
        raise RuntimeError("DoorSessionStore not initialized. Call init_dependencies() first.")
    return store


# ============================================================================
# Optional Getters (may return None)
# ============================================================================


def get_session_store_optional() -> Optional[SessionStore]:
    """SessionStore 인스턴스 반환 (None 허용)."""
    return _instances.get("session_store")


def get_yolo_optional() -> Optional[YOLOWrapper]:
    """YOLOWrapper 인스턴스 반환 (None 허용)."""
    return _instances.get("yolo")


def get_decision_engine_optional() -> Optional[ProductDecisionEngine]:
    """ProductDecisionEngine 인스턴스 반환 (None 허용)."""
    return _instances.get("engine")


def get_product_db_optional() -> Optional[ProductDatabase]:
    """ProductDatabase 인스턴스 반환 (None 허용)."""
    return _instances.get("db")


def get_video_processor_optional() -> Optional[VideoProcessor]:
    """VideoProcessor 인스턴스 반환 (None 허용)."""
    return _instances.get("video_processor")


def get_door_session_store_optional() -> Optional[DoorSessionStore]:
    """DoorSessionStore 인스턴스 반환 (None 허용)."""
    return _instances.get("door_session_store")


# ============================================================================
# Status Check
# ============================================================================


def is_initialized() -> bool:
    """의존성 초기화 상태 확인."""
    required_keys = ["session_store", "yolo", "engine", "db", "video_processor"]
    # door_session_store는 선택적 (설정으로 비활성화 가능)
    return all(key in _instances for key in required_keys)


def get_status() -> dict:
    """의존성 상태 반환."""
    yolo = _instances.get("yolo")
    door_store = _instances.get("door_session_store")
    return {
        "initialized": is_initialized(),
        "session_store": _instances.get("session_store") is not None,
        "yolo": yolo is not None,
        "yolo_instance": yolo,  # health.py에서 is_loaded 확인용
        "yolo_loaded": yolo.is_loaded if yolo else False,
        "engine": _instances.get("engine") is not None,
        "db": _instances.get("db") is not None,
        "video_processor": _instances.get("video_processor") is not None,
        "door_session_store": door_store is not None,
        "door_session_store_instance": door_store,
    }
