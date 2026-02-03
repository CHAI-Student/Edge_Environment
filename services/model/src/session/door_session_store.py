"""
Door Session Store (v4.3).

Door Session을 관리하는 저장소.
여러 번의 /trigger 호출을 하나의 Door Session으로 통합 관리합니다.

v4.3 변경사항:
- GlobalDoorSession 추가: session_id="OPEN"/"CLOSE" 기반 문 상태 관리
- get_or_start_global_session(): OPEN 시 세션 생성/기존 유지
- finalize_global_session(): CLOSE 시 모든 zone 종료 및 결과 반환
- add_trigger_with_global(): trigger 시 GlobalSession 연동
- get_or_finalize()에서 GlobalSession 활성 시 타임아웃 무시

v4.2 변경사항:
- Copy-on-Write 패턴: Lock 내에서 데이터 복사, Lock 해제 후 YAML 저장
- 타임아웃 체크 로직 통합 (_check_timeout 메서드)

사용법:
    store = DoorSessionStore(
        yaml_dir="data/sessions",
        session_timeout=30.0,
        weight_tolerance=3.0,
    )

    # GlobalSession 기반 (v4.3)
    global_session = store.get_or_start_global_session()  # OPEN
    door_session = store.add_trigger_with_global(zone=1, result=trigger_result)
    result = store.finalize_global_session()  # CLOSE

    # 기존 방식 (v4.2 하위 호환)
    door_session = store.add_trigger(zone=1, result=trigger_result)
    session, is_finalized = store.get_or_finalize(zone=1)
"""

import copy
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .door_session import (
    DoorSession,
    TriggerResult,
    AggregatedProduct,
    generate_door_session_id,
)
from .global_door_session import GlobalDoorSession, generate_global_session_id
from .product_aggregator import ProductAggregator
from .yaml_persistence import YamlPersistence

logger = logging.getLogger(__name__)


@dataclass
class TimeoutCheckResult:
    """타임아웃 체크 결과."""
    is_timed_out: bool
    reason: str = ""  # "idle_timeout" | "max_duration" | ""


class DoorSessionStore:
    """
    Door Session 저장소 (v4.3).

    Zone별로 하나의 활성 Door Session을 관리합니다.
    여러 trigger가 발생해도 같은 Door Session에 통합됩니다.

    v4.3: GlobalDoorSession 지원
    - session_id="OPEN" → get_or_start_global_session()
    - session_id="CLOSE" → finalize_global_session()
    - GlobalSession 활성 시 타임아웃 무시

    타임아웃 시 자동으로 세션이 finalize되며,
    YAML 파일로 영속화됩니다.
    """

    def __init__(
        self,
        yaml_dir: str = "data/sessions",
        session_timeout: float = 30.0,
        weight_tolerance: float = 3.0,
        max_duration: float = 600.0,
        get_product_weight: Optional[Callable[[int], float]] = None,
    ):
        """
        Initialize DoorSessionStore.

        Args:
            yaml_dir: YAML 저장 디렉토리
            session_timeout: 마지막 trigger 후 타임아웃 (초)
            weight_tolerance: 무게 매칭 허용 오차 (g)
            max_duration: 최대 세션 지속 시간 (초)
            get_product_weight: product_id -> weight 조회 함수
        """
        self._active_sessions: Dict[int, DoorSession] = {}  # zone -> session
        self._lock = threading.Lock()

        # v4.3: GlobalDoorSession
        self._global_session: Optional[GlobalDoorSession] = None

        self._session_timeout = session_timeout
        self._weight_tolerance = weight_tolerance
        self._max_duration = max_duration
        self._get_product_weight = get_product_weight

        # 컴포넌트 초기화
        self._persistence = YamlPersistence(base_dir=yaml_dir)
        self._aggregator = ProductAggregator(
            weight_tolerance=weight_tolerance,
            get_product_weight=get_product_weight,
        )

        logger.info(
            f"DoorSessionStore initialized: "
            f"timeout={session_timeout}s, tolerance={weight_tolerance}g, "
            f"max_duration={max_duration}s"
        )

    def _check_timeout(
        self,
        session: DoorSession,
        now: Optional[float] = None,
    ) -> TimeoutCheckResult:
        """
        세션 타임아웃 체크 (통합 로직, v4.2).

        Args:
            session: 체크할 DoorSession
            now: 현재 시각 (기본값: time.time())

        Returns:
            TimeoutCheckResult
        """
        if now is None:
            now = time.time()

        time_since_last = now - session.last_trigger_at
        total_duration = now - session.created_at

        if time_since_last > self._session_timeout:
            return TimeoutCheckResult(
                is_timed_out=True,
                reason="idle_timeout",
            )

        if total_duration > self._max_duration:
            return TimeoutCheckResult(
                is_timed_out=True,
                reason="max_duration",
            )

        return TimeoutCheckResult(is_timed_out=False)

    def set_product_weight_getter(
        self,
        get_product_weight: Callable[[int], float],
    ) -> None:
        """
        ProductDatabase 무게 조회 함수 설정.

        Args:
            get_product_weight: product_id -> weight 조회 함수
        """
        self._get_product_weight = get_product_weight
        self._aggregator = ProductAggregator(
            weight_tolerance=self._weight_tolerance,
            get_product_weight=get_product_weight,
        )

    def add_trigger(
        self,
        zone: int,
        result: TriggerResult,
    ) -> DoorSession:
        """
        Trigger 결과 추가.

        활성 세션이 없으면 새로 생성하고,
        있으면 기존 세션에 trigger를 추가합니다.

        v4.2: Copy-on-Write 패턴 - Lock 내에서 데이터 수정, Lock 해제 후 YAML 저장

        Args:
            zone: Zone 번호
            result: TriggerResult

        Returns:
            업데이트된 DoorSession
        """
        session_to_save: Optional[DoorSession] = None
        session_to_finalize: Optional[DoorSession] = None

        with self._lock:
            now = time.time()

            # 기존 세션 확인
            session = self._active_sessions.get(zone)

            if session is not None:
                # 타임아웃 체크 (통합 로직 사용)
                timeout_result = self._check_timeout(session, now)

                if timeout_result.is_timed_out:
                    if timeout_result.reason == "idle_timeout":
                        logger.info(
                            f"Door session timed out: {session.door_session_id} "
                            f"(idle for {now - session.last_trigger_at:.1f}s)"
                        )
                    else:
                        logger.warning(
                            f"Door session max duration exceeded: {session.door_session_id} "
                            f"(duration={now - session.created_at:.1f}s)"
                        )
                    # Lock 내에서 finalize 처리 (메모리 상태만)
                    self._finalize_session_in_memory(session)
                    session_to_finalize = session  # Lock 해제 후 YAML 저장
                    session = None

            if session is None:
                # 새 세션 생성
                session = DoorSession(
                    door_session_id=generate_door_session_id(zone),
                    zone=zone,
                    created_at=now,
                    last_trigger_at=now,
                )
                self._active_sessions[zone] = session
                logger.info(f"New door session created: {session.door_session_id}")

            # Trigger ID 생성
            result.trigger_id = f"trigger_{len(session.triggers) + 1:03d}"

            # Trigger 추가
            session.triggers.append(result)
            session.last_trigger_at = now

            # 상품 재집계
            self._reaggregate_products(session)

            # 저장할 세션 복사 (Lock 해제 후 저장)
            session_to_save = copy.deepcopy(session)

            logger.info(
                f"Trigger added to {session.door_session_id}: "
                f"id={result.trigger_id}, delta={result.delta_weight:.1f}g, "
                f"is_return={result.is_return}, "
                f"total_triggers={len(session.triggers)}"
            )

            return_session = session

        # Lock 해제 후 YAML 저장 (I/O 작업)
        if session_to_finalize is not None:
            self._persistence.save(session_to_finalize)

        if session_to_save is not None:
            self._persistence.save(session_to_save)

        return return_session

    def get_or_finalize(
        self,
        zone: int,
    ) -> Tuple[Optional[DoorSession], bool]:
        """
        세션 조회. 타임아웃 시 자동 finalize.

        v4.3: GlobalSession 활성 시 타임아웃 무시
        v4.2: Copy-on-Write 패턴, 통합 타임아웃 체크

        Args:
            zone: Zone 번호

        Returns:
            (DoorSession, is_finalized) 튜플
            - DoorSession: 세션 (없으면 None)
            - is_finalized: 이번 호출에서 finalize 되었는지 여부
        """
        session_to_save: Optional[DoorSession] = None
        return_session: Optional[DoorSession] = None
        is_finalized = False

        with self._lock:
            # v4.3: GlobalSession 활성이면 타임아웃 체크 안함
            if self._global_session is not None:
                session = self._active_sessions.get(zone)
                return session, False

            # 기존 로직 (GlobalSession 없을 때만)
            session = self._active_sessions.get(zone)

            if session is None:
                return None, False

            now = time.time()
            timeout_result = self._check_timeout(session, now)

            if timeout_result.is_timed_out:
                if timeout_result.reason == "idle_timeout":
                    logger.info(
                        f"Door session finalized (timeout): {session.door_session_id} "
                        f"(idle for {now - session.last_trigger_at:.1f}s)"
                    )
                else:
                    logger.warning(
                        f"Door session finalized (max duration): {session.door_session_id} "
                        f"(duration={now - session.created_at:.1f}s)"
                    )
                self._finalize_session_in_memory(session)
                session_to_save = copy.deepcopy(session)
                return_session = session
                is_finalized = True
            else:
                return_session = session

        # Lock 해제 후 YAML 저장 (I/O 작업)
        if session_to_save is not None:
            self._persistence.save(session_to_save)

        return return_session, is_finalized

    # ========================================================================
    # GlobalDoorSession Methods (v4.3)
    # ========================================================================

    def get_or_start_global_session(self) -> GlobalDoorSession:
        """
        GlobalSession 조회 또는 시작 (v4.3).

        session_id="OPEN" 시 호출됩니다.

        핵심: 이미 활성 GlobalSession이 있으면 기존 것 반환 (초기화 안함)
        없으면 새로 생성합니다.

        Returns:
            GlobalDoorSession (기존 또는 새로 생성된 것)
        """
        with self._lock:
            if self._global_session is not None:
                # 이미 활성 세션 있음 → 기존 것 반환
                logger.debug(
                    f"GlobalSession already active: {self._global_session.global_session_id}"
                )
                return self._global_session

            # 새 세션 생성
            self._global_session = GlobalDoorSession(
                global_session_id=generate_global_session_id(),
            )
            logger.info(
                f"GlobalSession started: {self._global_session.global_session_id}"
            )
            return self._global_session

    def finalize_global_session(self) -> Optional[GlobalDoorSession]:
        """
        GlobalSession 종료 (v4.3).

        session_id="CLOSE" 시 호출됩니다.
        모든 활성 zone의 DoorSession을 finalize하고 결과를 반환합니다.

        Returns:
            종료된 GlobalDoorSession 또는 None (활성 세션이 없는 경우)
        """
        sessions_to_save: List[DoorSession] = []

        with self._lock:
            if self._global_session is None:
                logger.warning("finalize_global_session called but no active session")
                return None

            # 모든 활성 zone 세션 finalize
            for zone in list(self._active_sessions.keys()):
                session = self._active_sessions[zone]
                self._finalize_session_in_memory(session)
                self._global_session.zone_sessions[zone] = session
                sessions_to_save.append(copy.deepcopy(session))

            self._global_session.status = "complete"
            self._global_session.finalized_at = time.time()

            result = self._global_session
            self._global_session = None

            logger.info(
                f"GlobalSession finalized: {result.global_session_id}, "
                f"zones={len(result.zone_sessions)}, "
                f"total_price={result.total_price}, "
                f"total_products={result.total_product_count}"
            )

        # Lock 해제 후 YAML 저장 (I/O 작업)
        for session in sessions_to_save:
            self._persistence.save(session)

        return result

    def get_global_session(self) -> Optional[GlobalDoorSession]:
        """
        현재 활성 GlobalSession 반환 (v4.3).

        Returns:
            GlobalDoorSession 또는 None
        """
        with self._lock:
            return self._global_session

    def is_global_session_active(self) -> bool:
        """
        GlobalSession 활성 여부 (v4.3).

        Returns:
            True if GlobalSession is active
        """
        with self._lock:
            return self._global_session is not None

    def add_trigger_with_global(
        self,
        zone: int,
        result: TriggerResult,
    ) -> DoorSession:
        """
        Trigger 결과 추가 + GlobalSession 연동 (v4.3).

        기존 add_trigger를 호출하고,
        GlobalSession이 활성이면 해당 zone의 DoorSession을 연동합니다.

        Args:
            zone: Zone 번호
            result: TriggerResult

        Returns:
            업데이트된 DoorSession
        """
        # 기존 add_trigger 호출
        door_session = self.add_trigger(zone=zone, result=result)

        # GlobalSession에 연동
        with self._lock:
            if self._global_session is not None:
                self._global_session.zone_sessions[zone] = door_session
                logger.debug(
                    f"Door session linked to GlobalSession: zone={zone}, "
                    f"global_id={self._global_session.global_session_id}"
                )

        return door_session

    # ========================================================================
    # Original Methods (continued)
    # ========================================================================

    def get_session(self, zone: int) -> Optional[DoorSession]:
        """
        세션 조회 (타임아웃 체크 없음).

        Args:
            zone: Zone 번호

        Returns:
            DoorSession 또는 None
        """
        with self._lock:
            return self._active_sessions.get(zone)

    def finalize_session(self, zone: int) -> Optional[DoorSession]:
        """
        세션 강제 종료.

        v4.2: Copy-on-Write 패턴

        Args:
            zone: Zone 번호

        Returns:
            종료된 DoorSession 또는 None
        """
        session_to_save: Optional[DoorSession] = None

        with self._lock:
            session = self._active_sessions.get(zone)
            if session is not None:
                self._finalize_session_in_memory(session)
                session_to_save = copy.deepcopy(session)
            else:
                return None

        # Lock 해제 후 YAML 저장 (I/O 작업)
        if session_to_save is not None:
            self._persistence.save(session_to_save)

        return session_to_save

    def _finalize_session_in_memory(self, session: DoorSession) -> None:
        """
        세션 종료 처리 - 메모리 상태만 변경 (내부용, lock 내에서 호출).

        v4.2: YAML 저장은 Lock 해제 후 별도로 수행

        Args:
            session: 종료할 DoorSession
        """
        session.status = "complete"
        session.finalized_at = time.time()

        # 활성 세션에서 제거
        if session.zone in self._active_sessions:
            del self._active_sessions[session.zone]

        logger.info(
            f"Door session finalized: {session.door_session_id}, "
            f"triggers={len(session.triggers)}, "
            f"products={session.product_count}, "
            f"total_price={session.total_price}"
        )

    def _finalize_session(self, session: DoorSession) -> None:
        """
        세션 종료 처리 - 메모리 + YAML (레거시 호환, lock 내에서 호출).

        주의: 이 메서드는 Lock 내에서 I/O를 수행하므로 새 코드에서는
        _finalize_session_in_memory + Lock 해제 후 save 패턴 사용 권장.

        Args:
            session: 종료할 DoorSession
        """
        self._finalize_session_in_memory(session)
        self._persistence.save(session)

    def _reaggregate_products(self, session: DoorSession) -> None:
        """
        세션의 상품 재집계 (내부용, lock 내에서 호출).

        v4.2: unmatched_returns 추적 추가

        Args:
            session: 재집계할 DoorSession
        """
        # 전체 trigger에서 상품 재집계 (unmatched_returns 포함)
        result = self._aggregator.aggregate_with_unmatched(session.triggers)
        session.aggregated_products = result.products
        session.unmatched_returns = result.unmatched_returns

        # 무게 정보 업데이트
        if self._get_product_weight is not None:
            self._aggregator.update_weights_from_db(
                session.aggregated_products,
                self._get_product_weight,
            )

    def recover_active_sessions(self) -> int:
        """
        서비스 시작 시 활성 세션 복구.

        v4.2: 통합 타임아웃 체크, Copy-on-Write

        Returns:
            복구된 세션 수
        """
        sessions_to_save: List[DoorSession] = []

        with self._lock:
            recovered = self._persistence.recover_active_sessions()
            now = time.time()

            for zone, session in recovered.items():
                # 타임아웃 체크 (통합 로직 사용)
                timeout_result = self._check_timeout(session, now)

                if timeout_result.is_timed_out:
                    # 이미 타임아웃됨 → finalize
                    logger.info(
                        f"Recovered session already timed out: {session.door_session_id}"
                    )
                    session.status = "complete"
                    session.finalized_at = now
                    sessions_to_save.append(copy.deepcopy(session))
                else:
                    # 아직 활성 → 복구
                    self._active_sessions[zone] = session
                    logger.info(
                        f"Recovered active session: {session.door_session_id} "
                        f"(idle for {now - session.last_trigger_at:.1f}s)"
                    )

            active_count = len(self._active_sessions)

        # Lock 해제 후 YAML 저장 (I/O 작업)
        for session in sessions_to_save:
            self._persistence.save(session)

        return active_count

    def get_stats(self) -> dict:
        """
        저장소 통계 반환.

        v4.3: GlobalSession 정보 추가

        Returns:
            통계 정보
        """
        with self._lock:
            active_zones = list(self._active_sessions.keys())
            persistence_stats = self._persistence.get_stats()

            # v4.3: GlobalSession 정보
            global_session_info = None
            if self._global_session is not None:
                global_session_info = {
                    "global_session_id": self._global_session.global_session_id,
                    "status": self._global_session.status,
                    "zone_count": len(self._global_session.zone_sessions),
                    "active_zones": self._global_session.active_zones,
                    "total_trigger_count": self._global_session.total_trigger_count,
                    "total_price": self._global_session.total_price,
                    "duration_seconds": round(self._global_session.duration_seconds, 1),
                }

            return {
                "active_sessions": len(self._active_sessions),
                "active_zones": active_zones,
                "session_timeout": self._session_timeout,
                "weight_tolerance": self._weight_tolerance,
                "max_duration": self._max_duration,
                "global_session_active": self._global_session is not None,
                "global_session": global_session_info,
                **persistence_stats,
            }

    def clear_all(self) -> None:
        """모든 활성 세션 정리 (v4.2: Copy-on-Write)."""
        sessions_to_save: List[DoorSession] = []

        with self._lock:
            for session in list(self._active_sessions.values()):
                self._finalize_session_in_memory(session)
                sessions_to_save.append(copy.deepcopy(session))
            self._active_sessions.clear()

        # Lock 해제 후 YAML 저장 (I/O 작업)
        for session in sessions_to_save:
            self._persistence.save(session)

        logger.info(f"All {len(sessions_to_save)} door sessions cleared")
