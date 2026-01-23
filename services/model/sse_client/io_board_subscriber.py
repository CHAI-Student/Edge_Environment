"""
IO Board SSE Subscriber.

io_board의 SSE 스트림을 구독하여 실시간 이벤트를 수신합니다.

사용 예시:
    subscriber = IOBoardSubscriber(callback=on_loadcell_change)
    await subscriber.start()
"""

import asyncio
import logging
from typing import Callable, Optional, Any
from dataclasses import dataclass, field

import httpx

from .event_parser import (
    SSEEventParser,
    LoadcellChangeEvent,
    LoadcellUpdateEvent,
    LoadcellUncertaintyEvent,
    DoorUpdateEvent,
    SSEErrorEvent,
)
from .zone_detector import ZoneDetector, ZoneChangeInfo
from ..config import config

logger = logging.getLogger(__name__)


@dataclass
class SubscriberState:
    """구독자 상태."""

    connected: bool = False
    last_update_time: Optional[float] = None
    last_change_time: Optional[float] = None
    reconnect_count: int = 0
    error_count: int = 0
    consecutive_failures: int = 0  # 연속 실패 횟수
    last_error_time: Optional[float] = None
    last_error_message: Optional[str] = None


class IOBoardSubscriber:
    """
    IO Board SSE 구독자.

    loadcell.change 이벤트를 실시간으로 수신하여 콜백을 호출합니다.

    Attributes:
        base_url: io_board URL
        on_change: loadcell.change 이벤트 콜백
        on_update: loadcell.update 이벤트 콜백 (옵션)
        on_uncertainty: loadcell.uncertainty 이벤트 콜백 (옵션)
        on_door_update: door.update 이벤트 콜백 (옵션)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        on_change: Optional[Callable[[LoadcellChangeEvent, ZoneChangeInfo], Any]] = None,
        on_update: Optional[Callable[[LoadcellUpdateEvent], Any]] = None,
        on_uncertainty: Optional[Callable[[LoadcellUncertaintyEvent], Any]] = None,
        on_door_update: Optional[Callable[[DoorUpdateEvent], Any]] = None,
        on_error: Optional[Callable[[SSEErrorEvent], Any]] = None,
        on_connection_status: Optional[Callable[[bool, Optional[str]], Any]] = None,
        filter_method: str = "exponential",
        filter_alpha: float = 0.2,
        threshold: float = 5.0,
        threshold_scope: str = "filtered",
        loadcell_interval: float = 0.5,
        door_interval: float = 1.0,
        # Exponential Backoff 설정
        initial_reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 30.0,
        backoff_multiplier: float = 2.0,
        max_reconnect_attempts: int = -1,  # -1 = 무한
    ):
        """
        초기화.

        Args:
            base_url: io_board 서비스 URL
            on_change: loadcell.change 이벤트 콜백
            on_update: loadcell.update 이벤트 콜백
            on_uncertainty: loadcell.uncertainty 이벤트 콜백
            on_door_update: door.update 이벤트 콜백
            on_error: error 이벤트 콜백
            on_connection_status: 연결 상태 변경 콜백 (connected, error_message)
            filter_method: 필터 방식 (none, exponential, kalman)
            filter_alpha: Exponential smoothing alpha
            threshold: 변화 감지 임계값 (g)
            threshold_scope: 임계값 적용 대상 (raw, filtered)
            loadcell_interval: 로드셀 폴링 간격 (초)
            door_interval: 도어 상태 폴링 간격 (초)
            initial_reconnect_delay: 초기 재연결 대기 시간 (초)
            max_reconnect_delay: 최대 재연결 대기 시간 (초)
            backoff_multiplier: 재연결 대기 시간 증가 배수
            max_reconnect_attempts: 최대 재연결 시도 (-1 = 무한)
        """
        self.base_url = base_url or config.io_board_url
        self.on_change = on_change
        self.on_update = on_update
        self.on_uncertainty = on_uncertainty
        self.on_door_update = on_door_update
        self.on_error = on_error
        self.on_connection_status = on_connection_status

        # SSE 파라미터
        self.filter_method = filter_method
        self.filter_alpha = filter_alpha
        self.threshold = threshold
        self.threshold_scope = threshold_scope
        self.loadcell_interval = loadcell_interval
        self.door_interval = door_interval

        # Exponential Backoff 설정
        self.initial_reconnect_delay = initial_reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.backoff_multiplier = backoff_multiplier
        self.max_reconnect_attempts = max_reconnect_attempts
        self._current_reconnect_delay = initial_reconnect_delay

        # 상태
        self.state = SubscriberState()
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Zone 감지기
        self.zone_detector = ZoneDetector()

        # HTTP 클라이언트
        self._client: Optional[httpx.AsyncClient] = None

    def _build_sse_url(self) -> str:
        """SSE URL 생성."""
        params = [
            f"streams=loadcells,doors",
            f"loadcell_interval={self.loadcell_interval}",
            f"door_interval={self.door_interval}",
            f"filter_method={self.filter_method}",
            f"filter_alpha={self.filter_alpha}",
            f"threshold={self.threshold}",
            f"threshold_scope={self.threshold_scope}",
        ]
        return f"{self.base_url}/sse?{'&'.join(params)}"

    async def start(self) -> None:
        """구독 시작."""
        if self._running:
            logger.warning("Subscriber already running")
            return

        self._running = True
        self._client = httpx.AsyncClient(timeout=None)  # SSE는 타임아웃 없음
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"IOBoardSubscriber started: {self.base_url}")

    async def stop(self) -> None:
        """구독 중지."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
            self._client = None
        self.state.connected = False
        logger.info("IOBoardSubscriber stopped")

    async def _run_loop(self) -> None:
        """메인 실행 루프 (Exponential Backoff 재연결 포함)."""
        import time as time_module

        while self._running:
            try:
                await self._connect_and_stream()

                # 성공적인 연결 후 재연결 지연 초기화
                self._current_reconnect_delay = self.initial_reconnect_delay
                self.state.consecutive_failures = 0

            except asyncio.CancelledError:
                break

            except Exception as e:
                error_msg = str(e)
                logger.error(f"SSE connection error: {error_msg}")

                self.state.connected = False
                self.state.error_count += 1
                self.state.consecutive_failures += 1
                self.state.last_error_time = time_module.time()
                self.state.last_error_message = error_msg

                # 연결 상태 콜백 호출
                if self.on_connection_status:
                    try:
                        result = self.on_connection_status(False, error_msg)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as cb_err:
                        logger.error(f"Connection status callback error: {cb_err}")

                # 최대 재연결 시도 확인
                if self.max_reconnect_attempts >= 0:
                    if self.state.reconnect_count >= self.max_reconnect_attempts:
                        logger.error(
                            f"Max reconnect attempts ({self.max_reconnect_attempts}) reached, "
                            f"giving up"
                        )
                        break

                self.state.reconnect_count += 1

                # Exponential Backoff 적용
                delay = self._current_reconnect_delay
                logger.info(
                    f"Reconnecting in {delay:.1f}s "
                    f"(attempt {self.state.reconnect_count}, "
                    f"consecutive failures: {self.state.consecutive_failures})"
                )

                await asyncio.sleep(delay)

                # 다음 재연결을 위해 지연 시간 증가
                self._current_reconnect_delay = min(
                    self._current_reconnect_delay * self.backoff_multiplier,
                    self.max_reconnect_delay
                )

    async def _connect_and_stream(self) -> None:
        """SSE 연결 및 스트림 처리."""
        url = self._build_sse_url()
        logger.info(f"Connecting to SSE: {url}")

        async with self._client.stream("GET", url) as response:
            if response.status_code != 200:
                raise Exception(f"SSE connection failed: {response.status_code}")

            self.state.connected = True
            self.state.reconnect_count = 0
            self.state.consecutive_failures = 0
            self._current_reconnect_delay = self.initial_reconnect_delay
            logger.info("SSE connected successfully")

            # 연결 성공 콜백 호출
            if self.on_connection_status:
                try:
                    result = self.on_connection_status(True, None)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as cb_err:
                    logger.error(f"Connection status callback error: {cb_err}")

            event_type = None
            event_data = None

            async for line in response.aiter_lines():
                if not self._running:
                    break

                line = line.strip()
                if not line:
                    # 빈 줄 = 이벤트 완료
                    if event_type and event_data:
                        await self._handle_event(event_type, event_data)
                    event_type = None
                    event_data = None
                    continue

                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    event_data = line[5:].strip()

    async def _handle_event(self, event_type: str, event_data: str) -> None:
        """이벤트 처리."""
        import time

        event = SSEEventParser.parse(event_type, event_data)
        if not event:
            return

        if isinstance(event, LoadcellChangeEvent):
            self.state.last_change_time = time.time()

            # Zone 감지
            zone_info = self.zone_detector.get_primary_zone(
                event.changed_indices,
                event.old_values,
                event.new_values,
            )

            logger.info(
                f"LoadCell CHANGE: indices={event.changed_indices}, "
                f"deltas={event.deltas}, zone={zone_info.zone_id if zone_info else None}"
            )

            if self.on_change and zone_info:
                try:
                    result = self.on_change(event, zone_info)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Error in on_change callback: {e}")

        elif isinstance(event, LoadcellUpdateEvent):
            self.state.last_update_time = time.time()
            if self.on_update:
                try:
                    result = self.on_update(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Error in on_update callback: {e}")

        elif isinstance(event, LoadcellUncertaintyEvent):
            logger.warning(
                f"LoadCell UNCERTAINTY: indices={event.affected_indices}, "
                f"reason={event.reason}"
            )
            if self.on_uncertainty:
                try:
                    result = self.on_uncertainty(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Error in on_uncertainty callback: {e}")

        elif isinstance(event, DoorUpdateEvent):
            if self.on_door_update:
                try:
                    result = self.on_door_update(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Error in on_door_update callback: {e}")

        elif isinstance(event, SSEErrorEvent):
            logger.error(f"SSE Error: {event.error_code} - {event.message}")
            if self.on_error:
                try:
                    result = self.on_error(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Error in on_error callback: {e}")

    @property
    def is_connected(self) -> bool:
        """연결 상태."""
        return self.state.connected

    @property
    def is_running(self) -> bool:
        """실행 상태."""
        return self._running

    def reset_backoff(self) -> None:
        """Backoff 상태 초기화."""
        self._current_reconnect_delay = self.initial_reconnect_delay
        self.state.consecutive_failures = 0
        self.state.reconnect_count = 0

    def get_connection_stats(self) -> dict:
        """
        연결 상태 통계.

        Returns:
            연결 상태 정보 딕셔너리
        """
        import time as time_module

        uptime = None
        if self.state.connected and self.state.last_update_time:
            uptime = time_module.time() - self.state.last_update_time

        return {
            "connected": self.state.connected,
            "running": self._running,
            "reconnect_count": self.state.reconnect_count,
            "error_count": self.state.error_count,
            "consecutive_failures": self.state.consecutive_failures,
            "current_backoff_delay": self._current_reconnect_delay,
            "last_update_time": self.state.last_update_time,
            "last_change_time": self.state.last_change_time,
            "last_error_time": self.state.last_error_time,
            "last_error_message": self.state.last_error_message,
        }
