"""
Global Door Session Data Model (v4.3).

전체 zone(1~5)을 통합 관리하는 GlobalDoorSession.
Node.js가 session_id="OPEN"/"CLOSE" 신호를 보내면,
문 열림~닫힘 동안의 모든 zone trigger를 하나의 세션으로 통합합니다.

사용법:
    global_session = GlobalDoorSession(
        global_session_id=generate_global_session_id(),
    )

    # zone별 DoorSession 추가
    global_session.zone_sessions[1] = door_session_zone_1

    # 전체 통계
    print(global_session.total_price)
    print(global_session.total_product_count)
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from .door_session import DoorSession


@dataclass
class GlobalDoorSession:
    """
    전체 zone 통합 관리 세션 (v4.3).

    문 열림(OPEN) ~ 문 닫힘(CLOSE) 동안의 모든 zone trigger를 통합 관리.
    Node.js가 session_id="OPEN"을 처음 보내면 생성,
    session_id="CLOSE"를 보내면 종료.

    Attributes:
        global_session_id: GlobalSession ID (예: "global_260203_143000")
        status: 세션 상태 ("active" | "complete")
        zone_sessions: zone별 DoorSession (zone -> DoorSession)
        created_at: 세션 생성 시각 (epoch)
        finalized_at: 세션 종료 시각 (complete일 때만)
    """

    global_session_id: str
    status: str = "active"  # "active" | "complete"
    zone_sessions: Dict[int, DoorSession] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    finalized_at: Optional[float] = None

    @property
    def total_price(self) -> int:
        """모든 zone의 총 금액 (count > 0인 상품만)."""
        return sum(s.total_price for s in self.zone_sessions.values())

    @property
    def total_product_count(self) -> int:
        """모든 zone의 총 상품 수 (count > 0인 상품만)."""
        return sum(s.product_count for s in self.zone_sessions.values())

    @property
    def is_active(self) -> bool:
        """활성 상태 여부."""
        return self.status == "active"

    @property
    def total_trigger_count(self) -> int:
        """모든 zone의 총 trigger 수."""
        return sum(s.trigger_count for s in self.zone_sessions.values())

    @property
    def duration_seconds(self) -> float:
        """세션 지속 시간 (초)."""
        end_time = self.finalized_at or time.time()
        return end_time - self.created_at

    @property
    def active_zones(self) -> list:
        """활성 zone 목록 (trigger가 있는 zone)."""
        return sorted(self.zone_sessions.keys())

    def get_zone_session(self, zone: int) -> Optional[DoorSession]:
        """특정 zone의 DoorSession 반환."""
        return self.zone_sessions.get(zone)

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "global_session_id": self.global_session_id,
            "status": self.status,
            "zone_sessions": {
                zone: session.to_dict()
                for zone, session in self.zone_sessions.items()
            },
            "created_at": self.created_at,
            "finalized_at": self.finalized_at,
            "summary": {
                "total_price": self.total_price,
                "total_product_count": self.total_product_count,
                "total_trigger_count": self.total_trigger_count,
                "zone_count": len(self.zone_sessions),
                "active_zones": self.active_zones,
                "duration_seconds": round(self.duration_seconds, 1),
            },
        }


def generate_global_session_id() -> str:
    """
    Global Session ID 생성.

    Format: global_{YYMMDD}_{HHMMSS}

    Returns:
        Global Session ID (예: global_260203_143000)
    """
    now = datetime.now()
    return f"global_{now.strftime('%y%m%d_%H%M%S')}"
