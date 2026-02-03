"""
Service Container for Dependency Injection.

의존성 주입을 위한 서비스 컨테이너.
전역 dict 대신 명시적인 인스턴스 관리로 테스트 격리를 보장합니다.

사용법:
    # 컨테이너 생성
    container = ServiceContainer()

    # 의존성 초기화
    container.init(
        session_store=session_store,
        yolo=yolo,
        engine=engine,
        product_db=product_db,
    )

    # 의존성 조회
    yolo = container.get_yolo()

    # 정리
    container.cleanup()

테스트에서:
    @pytest.fixture
    def container():
        c = ServiceContainer()
        c.init(...)
        yield c
        c.cleanup()  # 테스트 간 격리 보장

v4.5 변경사항:
- Global container에 threading.Lock() 추가 (race condition 방지)
- Double-checked locking 패턴 적용
"""

import logging
import threading
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from session import SessionStore, DoorSessionStore
    from session.active_product_store import ActiveProductStore
    from session.pending_trigger_store import PendingTriggerStore
    from vision import YOLOWrapper
    from database.product_db import ProductDatabase
    from engine import ProductDecisionEngine
    from video import VideoProcessor
    from service.trigger_service import TriggerService

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    서비스 컨테이너 - 의존성 라이프사이클 관리.

    Thread-safe하지 않음 (FastAPI lifespan에서 단일 스레드로 초기화).
    테스트에서는 각 테스트마다 새 인스턴스 생성 권장.
    """

    def __init__(self):
        """Initialize empty container."""
        self._session_store: Optional["SessionStore"] = None
        self._door_session_store: Optional["DoorSessionStore"] = None
        self._active_product_store: Optional["ActiveProductStore"] = None
        self._pending_trigger_store: Optional["PendingTriggerStore"] = None
        self._yolo: Optional["YOLOWrapper"] = None
        self._engine: Optional["ProductDecisionEngine"] = None
        self._product_db: Optional["ProductDatabase"] = None
        self._video_processor: Optional["VideoProcessor"] = None
        self._trigger_service: Optional["TriggerService"] = None
        self._initialized: bool = False

    def init(
        self,
        session_store: "SessionStore",
        yolo: "YOLOWrapper",
        engine: "ProductDecisionEngine",
        product_db: "ProductDatabase",
        video_processor: Optional["VideoProcessor"] = None,
        door_session_store: Optional["DoorSessionStore"] = None,
        active_product_store: Optional["ActiveProductStore"] = None,
        pending_trigger_store: Optional["PendingTriggerStore"] = None,
    ) -> None:
        """
        의존성 초기화.

        Args:
            session_store: SessionStore 인스턴스
            yolo: YOLOWrapper 인스턴스
            engine: ProductDecisionEngine 인스턴스
            product_db: ProductDatabase 인스턴스
            video_processor: VideoProcessor 인스턴스 (선택, 없으면 자동 생성)
            door_session_store: DoorSessionStore 인스턴스 (선택, v4.1)
            active_product_store: ActiveProductStore 인스턴스 (선택, v4.4)
            pending_trigger_store: PendingTriggerStore 인스턴스 (선택, v4.4)
        """
        from video import VideoProcessor
        from service.trigger_service import TriggerService

        self._session_store = session_store
        self._yolo = yolo
        self._engine = engine
        self._product_db = product_db
        self._door_session_store = door_session_store
        self._active_product_store = active_product_store
        self._pending_trigger_store = pending_trigger_store

        # VideoProcessor는 yolo를 공유
        if video_processor is not None:
            self._video_processor = video_processor
        else:
            self._video_processor = VideoProcessor(yolo=yolo)

        # TriggerService 생성 (v4.4)
        self._trigger_service = TriggerService(
            video_processor=self._video_processor,
            engine=engine,
            session_store=session_store,
            product_db=product_db,
            door_session_store=door_session_store,
            active_product_store=active_product_store,
            pending_trigger_store=pending_trigger_store,
        )

        self._initialized = True

        logger.info(
            f"ServiceContainer initialized: "
            f"session_store={session_store is not None}, "
            f"yolo={yolo is not None}, "
            f"engine={engine is not None}, "
            f"db={product_db is not None}, "
            f"video_processor={self._video_processor is not None}, "
            f"door_session_store={door_session_store is not None}, "
            f"active_product_store={active_product_store is not None}, "
            f"pending_trigger_store={pending_trigger_store is not None}"
        )

    def cleanup(self) -> None:
        """의존성 정리."""
        if self._session_store is not None:
            self._session_store.clear_all()

        if self._door_session_store is not None:
            self._door_session_store.clear_all()

        if self._active_product_store is not None:
            self._active_product_store.clear_all()

        if self._pending_trigger_store is not None:
            self._pending_trigger_store.clear_all()

        self._session_store = None
        self._door_session_store = None
        self._active_product_store = None
        self._pending_trigger_store = None
        self._yolo = None
        self._engine = None
        self._product_db = None
        self._video_processor = None
        self._trigger_service = None
        self._initialized = False

        logger.info("ServiceContainer cleaned up")

    # ========================================================================
    # Getters (raise RuntimeError if not initialized)
    # ========================================================================

    def get_session_store(self) -> "SessionStore":
        """SessionStore 인스턴스 반환."""
        if self._session_store is None:
            raise RuntimeError("SessionStore not initialized. Call init() first.")
        return self._session_store

    def get_yolo(self) -> "YOLOWrapper":
        """YOLOWrapper 인스턴스 반환."""
        if self._yolo is None:
            raise RuntimeError("YOLOWrapper not initialized. Call init() first.")
        return self._yolo

    def get_decision_engine(self) -> "ProductDecisionEngine":
        """ProductDecisionEngine 인스턴스 반환."""
        if self._engine is None:
            raise RuntimeError("ProductDecisionEngine not initialized. Call init() first.")
        return self._engine

    def get_product_db(self) -> "ProductDatabase":
        """ProductDatabase 인스턴스 반환."""
        if self._product_db is None:
            raise RuntimeError("ProductDatabase not initialized. Call init() first.")
        return self._product_db

    def get_video_processor(self) -> "VideoProcessor":
        """VideoProcessor 인스턴스 반환."""
        if self._video_processor is None:
            raise RuntimeError("VideoProcessor not initialized. Call init() first.")
        return self._video_processor

    def get_door_session_store(self) -> "DoorSessionStore":
        """DoorSessionStore 인스턴스 반환."""
        if self._door_session_store is None:
            raise RuntimeError("DoorSessionStore not initialized. Call init() first.")
        return self._door_session_store

    def get_active_product_store(self) -> "ActiveProductStore":
        """ActiveProductStore 인스턴스 반환 (v4.4)."""
        if self._active_product_store is None:
            raise RuntimeError("ActiveProductStore not initialized. Call init() first.")
        return self._active_product_store

    def get_pending_trigger_store(self) -> "PendingTriggerStore":
        """PendingTriggerStore 인스턴스 반환 (v4.4)."""
        if self._pending_trigger_store is None:
            raise RuntimeError("PendingTriggerStore not initialized. Call init() first.")
        return self._pending_trigger_store

    def get_trigger_service(self) -> "TriggerService":
        """TriggerService 인스턴스 반환 (v4.4)."""
        if self._trigger_service is None:
            raise RuntimeError("TriggerService not initialized. Call init() first.")
        return self._trigger_service

    # ========================================================================
    # Optional Getters (may return None)
    # ========================================================================

    def get_session_store_optional(self) -> Optional["SessionStore"]:
        """SessionStore 인스턴스 반환 (None 허용)."""
        return self._session_store

    def get_yolo_optional(self) -> Optional["YOLOWrapper"]:
        """YOLOWrapper 인스턴스 반환 (None 허용)."""
        return self._yolo

    def get_decision_engine_optional(self) -> Optional["ProductDecisionEngine"]:
        """ProductDecisionEngine 인스턴스 반환 (None 허용)."""
        return self._engine

    def get_product_db_optional(self) -> Optional["ProductDatabase"]:
        """ProductDatabase 인스턴스 반환 (None 허용)."""
        return self._product_db

    def get_video_processor_optional(self) -> Optional["VideoProcessor"]:
        """VideoProcessor 인스턴스 반환 (None 허용)."""
        return self._video_processor

    def get_door_session_store_optional(self) -> Optional["DoorSessionStore"]:
        """DoorSessionStore 인스턴스 반환 (None 허용)."""
        return self._door_session_store

    def get_active_product_store_optional(self) -> Optional["ActiveProductStore"]:
        """ActiveProductStore 인스턴스 반환 (None 허용, v4.4)."""
        return self._active_product_store

    def get_pending_trigger_store_optional(self) -> Optional["PendingTriggerStore"]:
        """PendingTriggerStore 인스턴스 반환 (None 허용, v4.4)."""
        return self._pending_trigger_store

    def get_trigger_service_optional(self) -> Optional["TriggerService"]:
        """TriggerService 인스턴스 반환 (None 허용, v4.4)."""
        return self._trigger_service

    # ========================================================================
    # Status
    # ========================================================================

    @property
    def is_initialized(self) -> bool:
        """초기화 상태 확인."""
        return self._initialized

    def get_status(self) -> dict:
        """의존성 상태 반환."""
        yolo = self._yolo
        door_store = self._door_session_store
        return {
            "initialized": self._initialized,
            "session_store": self._session_store is not None,
            "yolo": yolo is not None,
            "yolo_instance": yolo,  # health.py에서 is_loaded 확인용
            "yolo_loaded": yolo.is_loaded if yolo else False,
            "engine": self._engine is not None,
            "db": self._product_db is not None,
            "video_processor": self._video_processor is not None,
            "door_session_store": door_store is not None,
            "door_session_store_instance": door_store,
            "active_product_store": self._active_product_store is not None,
            "pending_trigger_store": self._pending_trigger_store is not None,
            "trigger_service": self._trigger_service is not None,
        }


# ============================================================================
# Global Container Instance (for FastAPI Depends compatibility)
# ============================================================================

# 전역 컨테이너 인스턴스 (FastAPI Depends 호환성 유지)
# 테스트에서는 이 인스턴스를 사용하지 말고 새로 생성할 것
_global_container: Optional[ServiceContainer] = None
_global_container_lock = threading.Lock()


def get_global_container() -> ServiceContainer:
    """
    전역 컨테이너 인스턴스 반환 (없으면 생성).

    Thread-safe: Double-checked locking 패턴 적용 (v4.5).
    """
    global _global_container
    # First check (without lock) - fast path
    if _global_container is not None:
        return _global_container

    # Second check (with lock) - slow path for initialization
    with _global_container_lock:
        if _global_container is None:
            _global_container = ServiceContainer()
            logger.debug("Global container created (thread-safe)")
        return _global_container


def set_global_container(container: ServiceContainer) -> None:
    """전역 컨테이너 설정 (테스트용). Thread-safe (v4.5)."""
    global _global_container
    with _global_container_lock:
        _global_container = container


def reset_global_container() -> None:
    """전역 컨테이너 리셋 (테스트 격리용). Thread-safe (v4.5)."""
    global _global_container
    with _global_container_lock:
        if _global_container is not None:
            _global_container.cleanup()
        _global_container = None
