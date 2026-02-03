"""
Pending Trigger Store (v4.4).

products 도착 전 대기 중인 trigger를 저장.
trigger가 Node.js 폴링(products)보다 먼저 올 경우 대기 처리용.

핵심 기능:
- Camera trigger 정보(videos, loadcells) 임시 저장
- products 도착 시 대기 중인 trigger 조회
- 처리 완료 후 자동 제거

사용법:
    store = PendingTriggerStore()

    # trigger 도착 시 (products 없으면)
    trigger_id = store.add(zone=1, videos=videos_dict, loadcells=loadcells_list)

    # products 도착 시 대기 trigger 확인
    pending = store.get_pending(zone=1)
    if pending:
        # YOLO 추론 실행
        store.remove(zone=1)
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingTrigger:
    """대기 중인 trigger 정보."""

    zone: int
    videos: Dict[str, str]  # {"top": path, "side": path}
    loadcells: List[Any]  # 로드셀 데이터 리스트
    created_at: float = field(default_factory=time.time)
    trigger_id: str = field(default_factory=lambda: f"pending_{uuid.uuid4().hex[:8]}")

    @property
    def age_seconds(self) -> float:
        """대기 시간 (초)."""
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "trigger_id": self.trigger_id,
            "zone": self.zone,
            "videos": self.videos,
            "loadcells_count": len(self.loadcells),
            "created_at": self.created_at,
            "age_seconds": round(self.age_seconds, 1),
        }


class PendingTriggerStore:
    """
    대기 중인 trigger 저장소.

    trigger가 products보다 먼저 도착할 때 사용.
    products 도착 후 대기 trigger를 처리하고 제거.

    Zone별로 최대 1개의 pending trigger만 유지.
    (새 trigger가 오면 기존 것 덮어씀)

    Thread-safe: 내부 Lock 사용.
    """

    # 대기 trigger 최대 보관 시간 (초)
    MAX_PENDING_AGE = 60.0

    def __init__(self):
        """Initialize PendingTriggerStore."""
        self._pending: Dict[int, PendingTrigger] = {}  # zone -> PendingTrigger
        self._lock = threading.Lock()

        logger.info("PendingTriggerStore initialized")

    def add(
        self,
        zone: int,
        videos: Dict[str, str],
        loadcells: List[Any],
    ) -> str:
        """
        대기 trigger 추가.

        기존에 같은 zone의 pending trigger가 있으면 덮어씀.

        Args:
            zone: Zone 번호
            videos: {"top": path, "side": path}
            loadcells: 로드셀 데이터 리스트

        Returns:
            생성된 trigger_id
        """
        pending = PendingTrigger(
            zone=zone,
            videos=videos,
            loadcells=loadcells,
        )

        with self._lock:
            # 기존 pending 있으면 로그
            if zone in self._pending:
                old = self._pending[zone]
                logger.warning(
                    f"[PendingTriggerStore] zone={zone}: "
                    f"replacing old pending trigger (age={old.age_seconds:.1f}s)"
                )

            self._pending[zone] = pending

        logger.info(
            f"[PendingTriggerStore] zone={zone}: "
            f"added pending trigger {pending.trigger_id}, "
            f"videos={list(videos.keys())}, loadcells={len(loadcells)}"
        )

        return pending.trigger_id

    def get_pending(self, zone: int) -> Optional[PendingTrigger]:
        """
        대기 중인 trigger 조회.

        너무 오래된 trigger는 자동 제거.

        Args:
            zone: Zone 번호

        Returns:
            PendingTrigger 또는 None
        """
        with self._lock:
            pending = self._pending.get(zone)

            if pending is None:
                return None

            # 너무 오래된 trigger는 제거
            if pending.age_seconds > self.MAX_PENDING_AGE:
                logger.warning(
                    f"[PendingTriggerStore] zone={zone}: "
                    f"pending trigger expired (age={pending.age_seconds:.1f}s > {self.MAX_PENDING_AGE}s)"
                )
                del self._pending[zone]
                return None

            return pending

    def remove(self, zone: int) -> bool:
        """
        처리 완료 후 pending trigger 제거.

        Args:
            zone: Zone 번호

        Returns:
            제거 성공 여부 (있었으면 True)
        """
        with self._lock:
            if zone in self._pending:
                pending = self._pending[zone]
                del self._pending[zone]
                logger.info(
                    f"[PendingTriggerStore] zone={zone}: "
                    f"removed pending trigger {pending.trigger_id} "
                    f"(waited {pending.age_seconds:.1f}s)"
                )
                return True
            return False

    def has_pending(self, zone: int) -> bool:
        """
        대기 중인 trigger 있는지 확인.

        만료된 trigger는 False 반환.

        Args:
            zone: Zone 번호

        Returns:
            대기 중인 trigger 존재 여부
        """
        pending = self.get_pending(zone)  # 만료 체크 포함
        return pending is not None

    def clear(self, zone: int) -> bool:
        """
        특정 zone의 pending trigger 삭제.

        remove()와 동일하지만 의미적으로 구분.

        Args:
            zone: Zone 번호

        Returns:
            삭제 성공 여부
        """
        return self.remove(zone)

    def clear_all(self) -> int:
        """
        모든 pending trigger 삭제.

        Returns:
            삭제된 trigger 수
        """
        with self._lock:
            count = len(self._pending)
            self._pending.clear()
            if count > 0:
                logger.info(f"[PendingTriggerStore] cleared all {count} pending triggers")
            return count

    def cleanup_expired(self) -> int:
        """
        만료된 pending trigger 정리.

        백그라운드 태스크에서 주기적으로 호출.

        Returns:
            정리된 trigger 수
        """
        expired_zones: List[int] = []
        now = time.time()

        with self._lock:
            for zone, pending in self._pending.items():
                if now - pending.created_at > self.MAX_PENDING_AGE:
                    expired_zones.append(zone)

            for zone in expired_zones:
                pending = self._pending.pop(zone)
                logger.warning(
                    f"[PendingTriggerStore] zone={zone}: "
                    f"expired pending trigger cleaned up "
                    f"(age={now - pending.created_at:.1f}s)"
                )

        return len(expired_zones)

    def get_stats(self) -> dict:
        """
        저장소 통계 반환.

        Returns:
            통계 정보
        """
        with self._lock:
            pending_list = []
            for zone, pending in self._pending.items():
                pending_list.append({
                    "zone": zone,
                    "trigger_id": pending.trigger_id,
                    "age_seconds": round(pending.age_seconds, 1),
                    "videos": list(pending.videos.keys()),
                    "loadcells_count": len(pending.loadcells),
                })

            return {
                "pending_count": len(self._pending),
                "pending_zones": list(self._pending.keys()),
                "max_pending_age": self.MAX_PENDING_AGE,
                "pending_triggers": pending_list,
            }
