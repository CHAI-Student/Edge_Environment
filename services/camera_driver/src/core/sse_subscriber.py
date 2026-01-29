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


@dataclass
class DoorEvent:
    """도어/데드볼트 이벤트 데이터"""
    door_state: str  # OPEN, CLOSED
    deadbolt_state: str  # OPEN, CLOSED
    timestamp: str
    raw_data: Dict[str, Any]


class IOBoardSSESubscriber:
    """
    IO Board SSE 구독자

    IO Board 서비스(8000)의 SSE 스트림을 구독하여
    loadcell.change 이벤트를 감지하고 콜백을 호출합니다.
    """

    def __init__(
        self,
        io_board_url: str = "http://localhost:8000",
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
        self._on_door_change: Optional[Callable[[DoorEvent], None]] = None

        # 연결 상태
        self._connected = False
        self._last_event_time: Optional[float] = None

        # 이전 도어 상태 (변화 감지용)
        self._last_deadbolt_state: Optional[str] = None

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

    def set_on_door_change(self, callback: Callable[[DoorEvent], None]):
        """도어/데드볼트 이벤트 콜백 설정"""
        self._on_door_change = callback

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
                print(f"[SSE_LOOP] Subscription loop error: {e}", flush=True)
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

            print(f"[SSE_LOOP] Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})", flush=True)
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

        print(f"[SSE_CONNECT] Attempting to connect to {sse_url}", flush=True)
        logger.info(f"Connecting to SSE: {sse_url}")

        try:
            async with self._session.get(sse_url) as response:
                if response.status != 200:
                    error_msg = f"SSE connection failed: HTTP {response.status}"
                    print(f"[SSE_CONNECT] ERROR: {error_msg}", flush=True)
                    raise ConnectionError(error_msg)

                self._connected = True
                self._reconnect_attempts = 0  # 연결 성공 시 리셋
                print(f"[SSE_CONNECT] Successfully connected, listening for events...", flush=True)
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

        except asyncio.CancelledError:
            print(f"[SSE_CONNECT] Subscription cancelled", flush=True)
            logger.info("SSE subscription cancelled")
            raise
        except Exception as e:
            self._connected = False
            print(f"[SSE_CONNECT] ERROR: {type(e).__name__}: {e}", flush=True)
            logger.error(f"SSE subscription error: {e}")
            # 재연결은 _subscribe_loop()에서 자동으로 처리됨
        finally:
            self._connected = False
            # 세션 정리 조건 개선:
            # - 여기서 생성한 세션이거나
            # - 서비스가 중지 상태이거나
            # - 세션이 닫힌 상태인 경우
            should_close = (
                session_created_here or
                not self._running or
                (self._session and self._session.closed)
            )
            if should_close and self._session:
                try:
                    if not self._session.closed:
                        await self._session.close()
                    self._session = None
                    logger.debug("SSE session closed and cleaned up")
                except Exception as e:
                    logger.warning(f"Error closing SSE session: {e}")
                    self._session = None  # 에러 시에도 참조 정리

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
        # door.update 이벤트 처리
        elif event_type == "door.update":
            await self._handle_door_update(data)

    async def _handle_door_update(self, data: Dict[str, Any]):
        """door.update 이벤트 처리"""
        deadbolt_state = data.get("deadbolt", "").upper()
        door_state = data.get("door", "").upper()
        timestamp = data.get("timestamp", "")

        # 데드볼트 상태 변화 감지
        if self._last_deadbolt_state != deadbolt_state:
            logger.info(f"Deadbolt state changed: {self._last_deadbolt_state} -> {deadbolt_state}")
            self._last_deadbolt_state = deadbolt_state

            # 이벤트 객체 생성
            event = DoorEvent(
                door_state=door_state,
                deadbolt_state=deadbolt_state,
                timestamp=timestamp,
                raw_data=data,
            )

            # 콜백 호출
            if self._on_door_change:
                try:
                    result = self._on_door_change(event)
                    if asyncio.iscoroutine(result):
                        try:
                            await result
                        except asyncio.CancelledError:
                            logger.debug("Door change callback cancelled")
                            raise
                        except Exception as async_error:
                            logger.error(f"Door change async callback error: {async_error}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Door change callback error: {e}")

    async def _handle_loadcell_change(self, data: Dict[str, Any]):
        """
        loadcell.change 이벤트 처리

        SSE 이벤트 형식:
        {
            "timestamp": "2026-01-29T15:24:23.406406Z",
            "changed_indices": [0, 9],
            "old_values": [-13.0, -1.0],
            "new_values": [13.0, 1.0],
            "deltas": [26.0, 2.0],
            "threshold": 0.0,
            "threshold_scope": "filtered"
        }
        """
        # changed_indices에서 채널 정보 추출
        changed_indices = data.get("changed_indices", [])
        if not changed_indices:
            logger.warning("No changed_indices in loadcell event, skipping")
            return

        # 각 변화된 채널에 대해 Zone 결정 및 이벤트 생성
        # Zone별로 그룹화 (여러 채널이 같은 Zone에 속할 수 있음)
        zone_events: Dict[int, Dict[str, Any]] = {}

        old_values = data.get("old_values", [])
        new_values = data.get("new_values", [])
        deltas = data.get("deltas", [])
        timestamp = data.get("timestamp", "")

        for idx, channel in enumerate(changed_indices):
            # 채널에서 Zone ID 결정
            zone_id = self._zone_mapping.get(channel)
            if zone_id is None:
                logger.warning(f"Channel {channel} not mapped to any zone, skipping")
                continue

            # Zone별 데이터 누적
            if zone_id not in zone_events:
                zone_events[zone_id] = {
                    "channels": [],
                    "old_values": [],
                    "new_values": [],
                    "deltas": [],
                }

            zone_events[zone_id]["channels"].append(channel)
            if idx < len(old_values):
                zone_events[zone_id]["old_values"].append(old_values[idx])
            if idx < len(new_values):
                zone_events[zone_id]["new_values"].append(new_values[idx])
            if idx < len(deltas):
                zone_events[zone_id]["deltas"].append(deltas[idx])

        # 각 Zone에 대해 이벤트 처리
        for zone_id, zone_data in zone_events.items():
            channels = zone_data["channels"]
            zone_old_values = zone_data["old_values"]
            zone_new_values = zone_data["new_values"]
            zone_deltas = zone_data["deltas"]

            # 총 무게 변화량 계산 (deltas 합산)
            total_delta = sum(zone_deltas)

            # 이벤트 객체 생성
            event = WeightChangeEvent(
                zone_id=zone_id,
                channels=channels,
                delta=total_delta,
                current=zone_new_values,
                previous=zone_old_values,
                timestamp=timestamp,
                raw_data=data,
            )

            logger.info(
                f"Weight change detected: Zone {zone_id}, "
                f"channels={channels}, delta={total_delta:.1f}g"
            )

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
