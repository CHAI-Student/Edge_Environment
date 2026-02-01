"""
Session Store for YOLO Inference Results.

YOLO 추론 결과를 세션별로 저장하고 관리.
TTL 기반 자동 정리 기능 포함.

사용법:
    store = SessionStore(ttl_seconds=300)

    # 결과 저장
    store.save("zone_1_260201_143025", session_data)

    # 결과 조회
    data = store.get("zone_1_260201_143025")
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ProductResult:
    """단일 상품 판단 결과."""
    product_id: int
    name: str
    count: int
    price: int
    confidence: float


@dataclass
class SessionData:
    """
    세션별 YOLO 추론 결과.

    Attributes:
        session_id: 세션 ID (예: zone_1_260201_143025)
        zone: Zone 번호
        products: 판단된 상품 목록
        total_price: 총 금액
        delta_weight: 무게 변화량 (g)
        created_at: 생성 시간 (timestamp)
        status: 처리 상태 ("processing" | "complete")
        confidence: 전체 신뢰도
        top_frames: Top 카메라 프레임 수
        side_frames: Side 카메라 프레임 수
        processing_time_ms: 처리 시간 (ms)
    """
    session_id: str
    zone: int
    products: List[ProductResult] = field(default_factory=list)
    total_price: int = 0
    delta_weight: float = 0.0
    created_at: float = field(default_factory=time.time)
    status: str = "processing"
    confidence: float = 0.0
    top_frames: int = 0
    side_frames: int = 0
    processing_time_ms: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "session_id": self.session_id,
            "zone": self.zone,
            "products": [
                {
                    "productId": p.product_id,
                    "name": p.name,
                    "count": p.count,
                    "price": p.price,
                    "confidence": round(p.confidence, 4),
                }
                for p in self.products
            ],
            "totalPrice": self.total_price,
            "delta_weight": round(self.delta_weight, 1),
            "created_at": self.created_at,
            "status": self.status,
            "confidence": round(self.confidence, 4),
            "stats": {
                "top_frames": self.top_frames,
                "side_frames": self.side_frames,
                "processing_time_ms": round(self.processing_time_ms, 1),
            },
        }


class SessionStore:
    """
    세션별 YOLO 추론 결과 저장소.

    Thread-safe한 dict 기반 구현.
    TTL 기반 자동 정리 기능 포함.
    """

    def __init__(self, ttl_seconds: int = 300, max_sessions: int = 100):
        """
        Initialize session store.

        Args:
            ttl_seconds: 세션 TTL (기본: 300초 = 5분)
            max_sessions: 최대 세션 수 (기본: 100)
        """
        self._store: Dict[str, SessionData] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions

        logger.info(
            f"SessionStore initialized: ttl={ttl_seconds}s, max={max_sessions}"
        )

    def save(self, session_id: str, data: SessionData) -> None:
        """
        세션 데이터 저장.

        Args:
            session_id: 세션 ID
            data: 세션 데이터
        """
        with self._lock:
            # 중복 세션 경고
            if session_id in self._store:
                logger.warning(f"Session overwritten: {session_id}")

            # 용량 초과 시 오래된 세션 정리
            if len(self._store) >= self._max_sessions:
                self._cleanup_oldest()

            self._store[session_id] = data
            logger.debug(f"Session saved: {session_id}")

    def get(self, session_id: str) -> Optional[SessionData]:
        """
        세션 데이터 조회.

        Args:
            session_id: 세션 ID

        Returns:
            SessionData or None if not found or expired
        """
        data, _ = self.get_with_status(session_id)
        return data

    def get_with_status(self, session_id: str) -> Tuple[Optional[SessionData], str]:
        """
        세션 데이터 조회 (상태 포함).

        Args:
            session_id: 세션 ID

        Returns:
            (SessionData, status) 튜플
            - status: "found" | "not_found" | "expired"
        """
        with self._lock:
            data = self._store.get(session_id)

            if data is None:
                return None, "not_found"

            # TTL 체크
            if time.time() - data.created_at > self._ttl_seconds:
                del self._store[session_id]
                logger.debug(f"Session expired and removed: {session_id}")
                return None, "expired"

            return data, "found"

    def delete(self, session_id: str) -> bool:
        """
        세션 삭제.

        Args:
            session_id: 세션 ID

        Returns:
            삭제 성공 여부
        """
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]
                logger.debug(f"Session deleted: {session_id}")
                return True
            return False

    def exists(self, session_id: str) -> bool:
        """
        세션 존재 여부 확인.

        Args:
            session_id: 세션 ID

        Returns:
            존재 여부 (TTL 만료된 경우 False)
        """
        return self.get(session_id) is not None

    def cleanup_expired(self) -> int:
        """
        만료된 세션 정리.

        Returns:
            정리된 세션 수
        """
        with self._lock:
            now = time.time()
            expired_keys = [
                key for key, data in self._store.items()
                if now - data.created_at > self._ttl_seconds
            ]

            for key in expired_keys:
                del self._store[key]

            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired sessions")

            return len(expired_keys)

    def _cleanup_oldest(self) -> None:
        """가장 오래된 세션 정리 (lock 내부에서 호출)."""
        if not self._store:
            return

        # 가장 오래된 세션 찾기
        oldest_key = min(
            self._store.keys(),
            key=lambda k: self._store[k].created_at
        )
        del self._store[oldest_key]
        logger.debug(f"Removed oldest session: {oldest_key}")

    def clear_all(self) -> None:
        """모든 세션 삭제."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            logger.info(f"Cleared all {count} sessions")

    def get_stats(self) -> dict:
        """
        저장소 통계 반환.

        Returns:
            통계 정보 dict
        """
        with self._lock:
            now = time.time()
            active_count = sum(
                1 for data in self._store.values()
                if now - data.created_at <= self._ttl_seconds
            )

            return {
                "total_sessions": len(self._store),
                "active_sessions": active_count,
                "ttl_seconds": self._ttl_seconds,
                "max_sessions": self._max_sessions,
            }

    @property
    def session_count(self) -> int:
        """현재 저장된 세션 수."""
        with self._lock:
            return len(self._store)


def generate_session_id(zone: int) -> str:
    """
    세션 ID 생성.

    Format: zone_{zone}_{YYMMDD}_{HHMMSS}

    Args:
        zone: Zone 번호

    Returns:
        세션 ID (예: zone_1_260201_143025)
    """
    now = datetime.now()
    return f"zone_{zone}_{now.strftime('%y%m%d_%H%M%S')}"
