"""
API Dependencies for Dependency Injection (v4.5).

FastAPI Depends()를 위한 의존성 제공자.
ServiceContainer를 통해 인스턴스에 접근합니다.

v4.5 변경사항:
- PendingTriggerStore 관련 제거

v4.2 변경사항:
- 전역 _instances dict를 ServiceContainer로 교체
- 테스트 격리 개선
- 하위 호환성 유지 (기존 함수 시그니처 동일)

v4.1 변경사항:
- DoorSessionStore 추가

v4.0 변경사항:
- FrameBuffer 제거
- SessionStore 추가
"""

import logging
from typing import Optional

from model_service.session import SessionStore, DoorSessionStore
from model_service.session.active_product_store import ActiveProductStore
from model_service.vision import YOLOWrapper
from model_service.engine import ProductDecisionEngine
from model_service.video import VideoProcessor
from model_service.service.trigger_service import TriggerService
from model_service.container import ServiceContainer
from model_service.container.service_container import get_global_container, set_global_container, reset_global_container

logger = logging.getLogger(__name__)


def init_dependencies(
    session_store: SessionStore,
    yolo: YOLOWrapper,
    engine: ProductDecisionEngine,
    video_processor: Optional[VideoProcessor] = None,
    door_session_store: Optional[DoorSessionStore] = None,
    active_product_store: Optional[ActiveProductStore] = None,
) -> ServiceContainer:
    """
    의존성 초기화 (lifespan에서 호출).

    Args:
        session_store: SessionStore 인스턴스
        yolo: YOLOWrapper 인스턴스
        engine: ProductDecisionEngine 인스턴스
        video_processor: VideoProcessor 인스턴스 (선택)
        door_session_store: DoorSessionStore 인스턴스 (선택, v4.1)
        active_product_store: ActiveProductStore 인스턴스 (선택, v4.5)

    Returns:
        초기화된 ServiceContainer 인스턴스
    """
    container = get_global_container()
    container.init(
        session_store=session_store,
        yolo=yolo,
        engine=engine,
        video_processor=video_processor,
        door_session_store=door_session_store,
        active_product_store=active_product_store,
    )
    return container


def cleanup_dependencies() -> None:
    """의존성 정리 (shutdown 시 호출)."""
    reset_global_container()


# ============================================================================
# Dependency Getters (for FastAPI Depends)
# ============================================================================


def get_session_store() -> SessionStore:
    """SessionStore 인스턴스 반환."""
    return get_global_container().get_session_store()


def get_yolo() -> YOLOWrapper:
    """YOLOWrapper 인스턴스 반환."""
    return get_global_container().get_yolo()


def get_decision_engine() -> ProductDecisionEngine:
    """ProductDecisionEngine 인스턴스 반환."""
    return get_global_container().get_decision_engine()


def get_video_processor() -> VideoProcessor:
    """VideoProcessor 인스턴스 반환."""
    return get_global_container().get_video_processor()


def get_door_session_store() -> DoorSessionStore:
    """DoorSessionStore 인스턴스 반환."""
    return get_global_container().get_door_session_store()


def get_active_product_store() -> ActiveProductStore:
    """ActiveProductStore 인스턴스 반환 (v4.5)."""
    return get_global_container().get_active_product_store()


def get_trigger_service() -> TriggerService:
    """TriggerService 인스턴스 반환 (v4.4)."""
    return get_global_container().get_trigger_service()


# ============================================================================
# Optional Getters (may return None)
# ============================================================================


def get_session_store_optional() -> Optional[SessionStore]:
    """SessionStore 인스턴스 반환 (None 허용)."""
    return get_global_container().get_session_store_optional()


def get_yolo_optional() -> Optional[YOLOWrapper]:
    """YOLOWrapper 인스턴스 반환 (None 허용)."""
    return get_global_container().get_yolo_optional()


def get_decision_engine_optional() -> Optional[ProductDecisionEngine]:
    """ProductDecisionEngine 인스턴스 반환 (None 허용)."""
    return get_global_container().get_decision_engine_optional()


def get_video_processor_optional() -> Optional[VideoProcessor]:
    """VideoProcessor 인스턴스 반환 (None 허용)."""
    return get_global_container().get_video_processor_optional()


def get_door_session_store_optional() -> Optional[DoorSessionStore]:
    """DoorSessionStore 인스턴스 반환 (None 허용)."""
    return get_global_container().get_door_session_store_optional()


def get_active_product_store_optional() -> Optional[ActiveProductStore]:
    """ActiveProductStore 인스턴스 반환 (None 허용, v4.5)."""
    return get_global_container().get_active_product_store_optional()


def get_trigger_service_optional() -> Optional[TriggerService]:
    """TriggerService 인스턴스 반환 (None 허용, v4.4)."""
    return get_global_container().get_trigger_service_optional()


# ============================================================================
# Status Check
# ============================================================================


def is_initialized() -> bool:
    """의존성 초기화 상태 확인."""
    return get_global_container().is_initialized


def get_status() -> dict:
    """의존성 상태 반환."""
    return get_global_container().get_status()


# ============================================================================
# Test Utilities
# ============================================================================


def create_test_container() -> ServiceContainer:
    """
    테스트용 새 컨테이너 생성.

    테스트 간 격리를 위해 전역 컨테이너 대신 새 인스턴스 사용.

    Returns:
        새 ServiceContainer 인스턴스
    """
    return ServiceContainer()


def use_test_container(container: ServiceContainer) -> None:
    """
    테스트용 컨테이너를 전역으로 설정.

    테스트 fixture에서 사용:
        @pytest.fixture
        def container():
            c = create_test_container()
            c.init(...)
            use_test_container(c)
            yield c
            cleanup_dependencies()  # 전역 컨테이너 리셋

    Args:
        container: 테스트용 ServiceContainer
    """
    set_global_container(container)
