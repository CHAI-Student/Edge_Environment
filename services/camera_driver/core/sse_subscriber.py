"""
IO Board SSE Subscriber for Camera Driver

IO Board 서비스의 SSE 스트림을 구독하여 loadcell.change 이벤트를 감지하고
EventRecordingManager를 통해 이미지/영상을 저장합니다.

Architecture:
    IO Board SSE (loadcell.change) → SSE Subscriber → EventRecordingManager
                                                    ↓
                                   HTTP POST → Node.js (media_paths)
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class WeightChangeEvent:
    """무게 변화 이벤트 데이터"""
    zone_id: int
    channels: list
    delta: float
    current: list
    previous: list
    timestamp: str
    raw_data: Dict[str, Any]


class IOBoardSSESubscriber:
    """
    IO Board SSE 구독자

    IO Board 서비스(8001)의 SSE 스트림을 구독하여
    loadcell.change 이벤트를 감지하고 콜백을 호출합니다.
    """

    def __init__(
        self,
        io_board_url: str = "http://localhost:8001",
        zone_mapping_path: Optional[str] = None,
    ):
        """
        초기화

        Args:
            io_board_url: IO Board 서비스 URL
            zone_mapping_path: Zone 매핑 설정 파일 경로
        """
        self.io_board_url = io_board_url
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None

        # 재연결 설정
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._base_reconnect_delay = 2.0  # 초기 재연결 딜레이
        self._max_reconnect_delay = 60.0  # 최대 재연결 딜레이

        # Zone 매핑 (채널 → Zone)
        self._zone_mapping = self._load_zone_mapping(zone_mapping_path)

        # 이벤트 콜백
        self._on_weight_change: Optional[Callable[[WeightChangeEvent], None]] = None

        # 연결 상태
        self._connected = False
        self._last_event_time: Optional[float] = None

    def _load_zone_mapping(self, config_path: Optional[str] = None) -> Dict[int, int]:
        """
        Zone 매핑 설정 로드

        Returns:
            채널 → Zone ID 매핑 딕셔너리
        """
        import os
        from pathlib import Path

        # 기본 매핑 (채널 0,1 → Zone 0, 채널 2,3 → Zone 1, ...)
        # 최대 5개 zone 지원
        default_mapping = {}
        for zone_id in range(5):  # 기본 fallback용, 실제로는 설정 파일에서 읽음
            for ch in [zone_id * 2, zone_id * 2 + 1]:
                default_mapping[ch] = zone_id

        if config_path is None:
            # 기본 경로: Edge_Environment/config/zone_mapping.json
            base_dir = Path(__file__).parent.parent.parent.parent
            config_path = str(base_dir / "config" / "zone_mapping.json")

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # zones 파싱
                if "zones" in data:
                    mapping = {}
                    for zone_id_str, zone_info in data["zones"].items():
                        zone_id = int(zone_id_str)
                        channels = zone_info.get("loadcell_channels", [])
                        for ch in channels:
                            mapping[ch] = zone_id
                    logger.info(f"Zone mapping loaded from {config_path}")
                    return mapping

            except Exception as e:
                logger.warning(f"Failed to load zone mapping: {e}, using default")

        return default_mapping

    def set_on_weight_change(self, callback: Callable[[WeightChangeEvent], None]):
        """무게 변화 이벤트 콜백 설정"""
        self._on_weight_change = callback

    async def start(self):
        """SSE 구독 시작"""
        if self._running:
            logger.warning("SSE subscriber already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._subscribe_loop())
        logger.info(f"SSE subscriber started: {self.io_board_url}")

    async def stop(self):
        """SSE 구독 중지"""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # 세션 정리 (안전하게)
        if self._session:
            try:
                if not self._session.closed:
                    await self._session.close()
            except Exception as e:
                logger.warning(f"Error closing session: {e}")
            finally:
                self._session = None

        self._connected = False
        logger.info("SSE subscriber stopped")

    async def _subscribe_loop(self):
        """SSE 구독 루프 (재연결 포함)"""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSE subscription error: {e}")

            if not self._running:
                break

            # 재연결 딜레이 (exponential backoff)
            delay = min(
                self._base_reconnect_delay * (2 ** self._reconnect_attempts),
                self._max_reconnect_delay
            )
            self._reconnect_attempts += 1

            if self._reconnect_attempts > self._max_reconnect_attempts:
                logger.error(f"Max reconnect attempts ({self._max_reconnect_attempts}) reached")
                # 리셋 후 다시 시도
                self._reconnect_attempts = 0
                delay = self._max_reconnect_delay

            logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})")
            await asyncio.sleep(delay)

    async def _connect_and_listen(self):
        """SSE 연결 및 이벤트 수신"""
        sse_url = f"{self.io_board_url}/sse?streams=loadcells,doors&loadcell_interval=0.5"

        # aiohttp 세션 생성 (try-finally로 정리 보장)
        session_created_here = False
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            session_created_here = True

        logger.info(f"Connecting to SSE: {sse_url}")

        try:
            async with self._session.get(sse_url) as response:
                if response.status != 200:
                    raise ConnectionError(f"SSE connection failed: HTTP {response.status}")

                self._connected = True
                self._reconnect_attempts = 0  # 연결 성공 시 리셋
                logger.info("SSE connected successfully")

                # SSE 이벤트 파싱
                event_type = None
                event_data = ""

                async for line in response.content:
                    if not self._running:
                        break

                    line = line.decode("utf-8").strip()

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        event_data = line[5:].strip()
                    elif line == "" and event_data:
                        # 이벤트 완료
                        await self._process_event(event_type, event_data)
                        event_type = None
                        event_data = ""

                # 스트림 종료 시 미완료 이벤트 처리
                if event_data:
                    logger.debug("Processing incomplete event at stream end")
                    await self._process_event(event_type, event_data)

        finally:
            self._connected = False
            # 여기서 생성한 세션만 정리 (재사용 세션은 유지)
            if session_created_here and self._session and not self._running:
                try:
                    await self._session.close()
                    self._session = None
                except Exception:
                    pass

    async def _process_event(self, event_type: Optional[str], event_data: str):
        """SSE 이벤트 처리"""
        import time

        try:
            data = json.loads(event_data)
        except json.JSONDecodeError:
            return

        self._last_event_time = time.time()

        # loadcell.change 이벤트 처리
        if event_type == "loadcell.change":
            await self._handle_loadcell_change(data)

    async def _handle_loadcell_change(self, data: Dict[str, Any]):
        """loadcell.change 이벤트 처리"""
        # Zone ID 결정
        zone_id = data.get("zone_id")
        channels = data.get("channels", [])

        if zone_id is None and channels:
            # 채널에서 Zone 추론
            zone_id = self._zone_mapping.get(channels[0], 0)

        if zone_id is None:
            zone_id = 0

        # 이벤트 객체 생성
        event = WeightChangeEvent(
            zone_id=zone_id,
            channels=channels,
            delta=data.get("delta", 0),
            current=data.get("current", []),
            previous=data.get("previous", []),
            timestamp=data.get("timestamp", ""),
            raw_data=data,
        )

        logger.info(f"Weight change detected: Zone {zone_id}, delta={event.delta}g")

        # 콜백 호출
        if self._on_weight_change:
            try:
                result = self._on_weight_change(event)
                # 코루틴인 경우 await (별도 try-except로 비동기 오류 구분)
                if asyncio.iscoroutine(result):
                    try:
                        await result
                    except asyncio.CancelledError:
                        logger.debug(f"Weight change callback cancelled for zone {zone_id}")
                        raise  # CancelledError는 상위로 전파
                    except Exception as async_error:
                        logger.error(f"Weight change async callback error: {async_error}")
            except asyncio.CancelledError:
                raise  # CancelledError는 전파
            except Exception as e:
                logger.error(f"Weight change callback error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """상태 조회"""
        return {
            "running": self._running,
            "connected": self._connected,
            "io_board_url": self.io_board_url,
            "reconnect_attempts": self._reconnect_attempts,
            "last_event_time": self._last_event_time,
        }

    @property
    def is_connected(self) -> bool:
        return self._connected
