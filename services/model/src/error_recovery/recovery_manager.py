"""
Recovery Manager.

서비스별 에러 복구 관리.

기능:
- IO Board 헬스 체크 및 복구
- 카메라 헬스 체크 및 재연결
- SSE 연결 모니터링
- 에러 이력 관리
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from collections import deque
from enum import Enum

from .error_codes import ErrorCode, ServiceError

logger = logging.getLogger(__name__)


class RecoveryStatus(str, Enum):
    """복구 상태."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"       # 일부 기능 제한
    RECOVERING = "recovering"   # 복구 시도 중
    FAILED = "failed"           # 복구 실패


@dataclass
class ServiceHealth:
    """서비스 헬스 상태."""
    service: str
    status: RecoveryStatus = RecoveryStatus.HEALTHY
    last_check: float = 0.0
    error_count: int = 0
    recovery_count: int = 0
    last_error: Optional[ServiceError] = None
    details: Dict = field(default_factory=dict)


class RecoveryManager:
    """
    통합 에러 복구 매니저.

    모든 서비스의 헬스 상태를 모니터링하고
    에러 발생 시 자동 복구를 시도합니다.
    """

    def __init__(
        self,
        max_error_history: int = 100,
        health_check_interval: float = 30.0,
        auto_recovery: bool = True,
    ):
        """
        초기화.

        Args:
            max_error_history: 최대 에러 이력 수
            health_check_interval: 헬스 체크 간격 (초)
            auto_recovery: 자동 복구 활성화
        """
        self.max_error_history = max_error_history
        self.health_check_interval = health_check_interval
        self.auto_recovery = auto_recovery

        # 서비스별 헬스 상태
        self._services: Dict[str, ServiceHealth] = {}

        # 에러 이력
        self._error_history: deque = deque(maxlen=max_error_history)

        # 복구 핸들러 등록
        self._recovery_handlers: Dict[str, Callable] = {}

        # 모니터링 태스크
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        # 클라이언트 참조 (lazy init)
        self._io_board_client = None
        self._camera_client = None
        self._sse_subscriber = None

    def register_service(self, service: str, recovery_handler: Optional[Callable] = None) -> None:
        """
        서비스 등록.

        Args:
            service: 서비스 이름
            recovery_handler: 복구 핸들러 함수
        """
        self._services[service] = ServiceHealth(service=service)
        if recovery_handler:
            self._recovery_handlers[service] = recovery_handler
        logger.info(f"Service registered: {service}")

    def set_clients(
        self,
        io_board_url: Optional[str] = None,
        camera_client: Optional[Any] = None,
        sse_subscriber: Optional[Any] = None,
    ) -> None:
        """
        클라이언트 설정.

        Args:
            io_board_url: IO Board 서비스 URL
            camera_client: CameraClient 인스턴스
            sse_subscriber: IOBoardSubscriber 인스턴스
        """
        if io_board_url:
            import httpx
            self._io_board_client = httpx.AsyncClient(
                base_url=io_board_url,
                timeout=5.0,
            )
        self._camera_client = camera_client
        self._sse_subscriber = sse_subscriber

    async def start_monitoring(self) -> None:
        """헬스 체크 모니터링 시작."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Recovery manager monitoring started")

    async def stop_monitoring(self) -> None:
        """헬스 체크 모니터링 중지."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._io_board_client:
            await self._io_board_client.aclose()

        logger.info("Recovery manager monitoring stopped")

    async def _monitor_loop(self) -> None:
        """모니터링 루프."""
        while self._running:
            try:
                await self._check_all_services()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            await asyncio.sleep(self.health_check_interval)

    async def _check_all_services(self) -> None:
        """모든 서비스 헬스 체크."""
        # IO Board 체크
        if "io_board" in self._services:
            await self._check_io_board()

        # Camera 체크
        if "camera" in self._services:
            await self._check_camera()

        # SSE 체크
        if "sse" in self._services:
            await self._check_sse()

    # =========================================================================
    # IO Board 헬스 체크
    # =========================================================================

    async def check_io_board_health(self) -> bool:
        """
        IO Board 헬스 체크.

        Returns:
            정상 여부
        """
        if not self._io_board_client:
            return False

        try:
            response = await self._io_board_client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"IO Board health check failed: {e}")
            return False

    async def _check_io_board(self) -> None:
        """IO Board 서비스 체크."""
        service_health = self._services.get("io_board")
        if not service_health:
            return

        healthy = await self.check_io_board_health()
        service_health.last_check = time.time()

        if healthy:
            service_health.status = RecoveryStatus.HEALTHY
            service_health.error_count = 0
        else:
            service_health.error_count += 1
            service_health.status = RecoveryStatus.DEGRADED

            # 자동 복구 시도
            if self.auto_recovery and service_health.error_count >= 3:
                await self._attempt_recovery("io_board")

    # =========================================================================
    # Camera 헬스 체크
    # =========================================================================

    async def check_camera_health(self) -> Dict[int, bool]:
        """
        카메라 헬스 체크.

        Returns:
            {camera_id: is_healthy} 딕셔너리
        """
        if not self._camera_client:
            return {}

        try:
            result = await self._camera_client.check_all_cameras()
            return {
                cam_id: info["connected"]
                for cam_id, info in result.get("cameras", {}).items()
            }
        except Exception as e:
            logger.debug(f"Camera health check failed: {e}")
            return {}

    async def _check_camera(self) -> None:
        """Camera 서비스 체크."""
        service_health = self._services.get("camera")
        if not service_health:
            return

        health_status = await self.check_camera_health()
        service_health.last_check = time.time()
        service_health.details["cameras"] = health_status

        if not health_status:
            service_health.error_count += 1
            service_health.status = RecoveryStatus.DEGRADED
        elif all(health_status.values()):
            service_health.status = RecoveryStatus.HEALTHY
            service_health.error_count = 0
        else:
            # 일부 카메라만 실패
            failed_count = sum(1 for h in health_status.values() if not h)
            service_health.status = RecoveryStatus.DEGRADED
            service_health.error_count = failed_count

            # 자동 복구 시도
            if self.auto_recovery:
                for cam_id, healthy in health_status.items():
                    if not healthy:
                        await self.attempt_camera_reconnect(cam_id)

    async def attempt_camera_reconnect(self, camera_id: int) -> bool:
        """
        카메라 재연결 시도.

        Args:
            camera_id: 카메라 ID

        Returns:
            재연결 성공 여부
        """
        if not self._camera_client:
            return False

        logger.info(f"Attempting camera {camera_id} reconnect...")

        try:
            # camera_driver의 재연결 API 호출
            response = await self._io_board_client.post(
                f"/camera/{camera_id}/reconnect"
            )
            success = response.status_code == 200

            if success:
                logger.info(f"Camera {camera_id} reconnected successfully")
            else:
                logger.warning(f"Camera {camera_id} reconnect failed")

            return success

        except Exception as e:
            logger.error(f"Camera reconnect error: {e}")
            return False

    async def rebuild_camera_mapping(self) -> bool:
        """
        카메라 매핑 재구성.

        USB 포트 변경 등으로 카메라 인덱스가 변경된 경우 사용.

        Returns:
            재구성 성공 여부
        """
        logger.info("Rebuilding camera mapping...")

        try:
            # camera_driver의 매핑 재구성 API 호출
            if self._io_board_client:
                response = await self._io_board_client.post("/cameras/rebuild-mapping")
                return response.status_code == 200
            return False

        except Exception as e:
            logger.error(f"Camera mapping rebuild error: {e}")
            return False

    # =========================================================================
    # SSE 헬스 체크
    # =========================================================================

    async def _check_sse(self) -> None:
        """SSE 연결 체크."""
        service_health = self._services.get("sse")
        if not service_health:
            return

        if self._sse_subscriber:
            connected = self._sse_subscriber.is_connected
            service_health.last_check = time.time()

            if connected:
                service_health.status = RecoveryStatus.HEALTHY
                service_health.error_count = 0
            else:
                service_health.error_count += 1
                service_health.status = RecoveryStatus.DEGRADED

                # SSE는 자체 재연결 로직이 있으므로 별도 복구 불필요
                stats = self._sse_subscriber.get_connection_stats()
                service_health.details.update(stats)

    # =========================================================================
    # 에러 처리 및 복구
    # =========================================================================

    def record_error(self, error: ServiceError) -> None:
        """
        에러 기록.

        Args:
            error: ServiceError 인스턴스
        """
        self._error_history.append(error)

        # 서비스 상태 업데이트
        if error.service in self._services:
            service_health = self._services[error.service]
            service_health.error_count += 1
            service_health.last_error = error

            if error.recoverable:
                service_health.status = RecoveryStatus.DEGRADED
            else:
                service_health.status = RecoveryStatus.FAILED

        logger.warning(f"Error recorded: [{error.code.value}] {error.message}")

    async def _attempt_recovery(self, service: str) -> bool:
        """
        서비스 복구 시도.

        Args:
            service: 서비스 이름

        Returns:
            복구 성공 여부
        """
        if service not in self._services:
            return False

        service_health = self._services[service]
        service_health.status = RecoveryStatus.RECOVERING

        logger.info(f"Attempting recovery for {service}...")

        success = False

        # 등록된 복구 핸들러 호출
        if service in self._recovery_handlers:
            try:
                handler = self._recovery_handlers[service]
                result = handler()
                if asyncio.iscoroutine(result):
                    success = await result
                else:
                    success = bool(result)
            except Exception as e:
                logger.error(f"Recovery handler error: {e}")

        if success:
            service_health.status = RecoveryStatus.HEALTHY
            service_health.recovery_count += 1
            service_health.error_count = 0
            logger.info(f"Recovery successful for {service}")
        else:
            service_health.status = RecoveryStatus.DEGRADED
            logger.warning(f"Recovery failed for {service}")

        return success

    # =========================================================================
    # 상태 조회
    # =========================================================================

    def get_overall_status(self) -> RecoveryStatus:
        """
        전체 시스템 상태.

        Returns:
            가장 심각한 상태
        """
        if not self._services:
            return RecoveryStatus.HEALTHY

        statuses = [s.status for s in self._services.values()]

        if RecoveryStatus.FAILED in statuses:
            return RecoveryStatus.FAILED
        if RecoveryStatus.RECOVERING in statuses:
            return RecoveryStatus.RECOVERING
        if RecoveryStatus.DEGRADED in statuses:
            return RecoveryStatus.DEGRADED

        return RecoveryStatus.HEALTHY

    def get_service_status(self, service: str) -> Optional[ServiceHealth]:
        """
        특정 서비스 상태 조회.

        Args:
            service: 서비스 이름

        Returns:
            ServiceHealth 또는 None
        """
        return self._services.get(service)

    def get_all_status(self) -> Dict[str, dict]:
        """
        모든 서비스 상태 조회.

        Returns:
            {service: status_dict} 딕셔너리
        """
        return {
            name: {
                "status": health.status.value,
                "last_check": health.last_check,
                "error_count": health.error_count,
                "recovery_count": health.recovery_count,
                "last_error": health.last_error.to_dict() if health.last_error else None,
                "details": health.details,
            }
            for name, health in self._services.items()
        }

    def get_error_history(self, limit: int = 20) -> List[dict]:
        """
        최근 에러 이력 조회.

        Args:
            limit: 최대 조회 수

        Returns:
            에러 이력 리스트
        """
        errors = list(self._error_history)[-limit:]
        return [e.to_dict() for e in errors]

    def clear_error_history(self) -> None:
        """에러 이력 초기화."""
        self._error_history.clear()
        logger.info("Error history cleared")
