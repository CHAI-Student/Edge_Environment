"""
SSE Event Parser.

io_board SSE 이벤트를 파싱합니다.

이벤트 타입:
- loadcell.update: 주기적 로드셀 값
- loadcell.change: 임계값 초과 변화 감지
- loadcell.uncertainty: 센서 오류 상태
- door.update: 도어/데드볼트 상태
- error: 통신 오류
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Union
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class LoadcellUpdateEvent:
    """loadcell.update 이벤트 데이터."""

    timestamp: str
    raw_values: List[str]  # 10채널, 예: ["+12345", "+00123", ...]
    filtered_values: List[str]
    filter_method: str  # "none", "exponential", "kalman"

    @classmethod
    def from_dict(cls, data: dict) -> "LoadcellUpdateEvent":
        """딕셔너리에서 생성."""
        return cls(
            timestamp=data.get("timestamp", ""),
            raw_values=data.get("raw_values", []),
            filtered_values=data.get("filtered_values", []),
            filter_method=data.get("filter_method", "none"),
        )

    def get_numeric_values(self, use_filtered: bool = True) -> List[float]:
        """숫자 값으로 변환 (에러 상태는 None으로)."""
        values = self.filtered_values if use_filtered else self.raw_values
        result = []
        for v in values:
            if v in ("EEEEEE", "VVVVVV"):
                result.append(0.0)  # 에러 상태
            else:
                try:
                    result.append(float(v))
                except ValueError:
                    result.append(0.0)
        return result


@dataclass
class LoadcellChangeEvent:
    """loadcell.change 이벤트 데이터 (핵심 이벤트)."""

    timestamp: str
    changed_indices: List[int]  # 변화 감지된 채널 인덱스
    old_values: List[float]
    new_values: List[float]
    deltas: List[float]
    threshold: Union[float, List[float]]
    threshold_scope: str  # "raw" or "filtered"

    @classmethod
    def from_dict(cls, data: dict) -> "LoadcellChangeEvent":
        """딕셔너리에서 생성."""
        return cls(
            timestamp=data.get("timestamp", ""),
            changed_indices=data.get("changed_indices", []),
            old_values=data.get("old_values", []),
            new_values=data.get("new_values", []),
            deltas=data.get("deltas", []),
            threshold=data.get("threshold", 0.0),
            threshold_scope=data.get("threshold_scope", "filtered"),
        )

    @property
    def total_delta(self) -> float:
        """총 무게 변화량 (부호 유지)."""
        return sum(self.deltas)

    @property
    def is_removal(self) -> bool:
        """상품 제거 여부 (무게 감소)."""
        # 새 값이 이전 값보다 작으면 제거
        for old, new in zip(self.old_values, self.new_values):
            if new < old:
                return True
        return False

    def get_delta_with_sign(self) -> float:
        """부호가 있는 총 델타값 반환."""
        total = 0.0
        for old, new in zip(self.old_values, self.new_values):
            total += (new - old)
        return total


@dataclass
class LoadcellUncertaintyEvent:
    """loadcell.uncertainty 이벤트 데이터."""

    timestamp: str
    affected_indices: List[int]
    reason: str  # "error_state" or "io_board_failure"
    details: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "LoadcellUncertaintyEvent":
        """딕셔너리에서 생성."""
        return cls(
            timestamp=data.get("timestamp", ""),
            affected_indices=data.get("affected_indices", []),
            reason=data.get("reason", ""),
            details=data.get("details", {}),
        )


@dataclass
class DoorUpdateEvent:
    """door.update 이벤트 데이터."""

    timestamp: str
    door: str  # "CLOSED", "OPENED", "ERROR_"
    deadbolt: str  # "CLOSED", "OPENED", "ERROR_"

    @classmethod
    def from_dict(cls, data: dict) -> "DoorUpdateEvent":
        """딕셔너리에서 생성."""
        return cls(
            timestamp=data.get("timestamp", ""),
            door=data.get("door", ""),
            deadbolt=data.get("deadbolt", ""),
        )

    @property
    def is_door_open(self) -> bool:
        """도어 열림 여부."""
        return "OPEN" in self.door.upper()

    @property
    def is_deadbolt_open(self) -> bool:
        """데드볼트 열림 여부."""
        return "OPEN" in self.deadbolt.upper()


@dataclass
class SSEErrorEvent:
    """error 이벤트 데이터."""

    stream: str  # "loadcells" or "doors"
    error_code: str
    message: str
    details: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "SSEErrorEvent":
        """딕셔너리에서 생성."""
        return cls(
            stream=data.get("stream", ""),
            error_code=data.get("error_code", ""),
            message=data.get("message", ""),
            details=data.get("details", {}),
        )


# 이벤트 타입 유니온
SSEEvent = Union[
    LoadcellUpdateEvent,
    LoadcellChangeEvent,
    LoadcellUncertaintyEvent,
    DoorUpdateEvent,
    SSEErrorEvent,
]


class SSEEventParser:
    """
    SSE 이벤트 파서.

    io_board에서 수신한 SSE 스트림을 파싱합니다.
    """

    EVENT_PARSERS = {
        "loadcell.update": LoadcellUpdateEvent.from_dict,
        "loadcell.change": LoadcellChangeEvent.from_dict,
        "loadcell.uncertainty": LoadcellUncertaintyEvent.from_dict,
        "door.update": DoorUpdateEvent.from_dict,
        "error": SSEErrorEvent.from_dict,
    }

    @classmethod
    def parse(cls, event_type: str, data: str) -> Optional[SSEEvent]:
        """
        SSE 이벤트 파싱.

        Args:
            event_type: 이벤트 타입 (예: "loadcell.change")
            data: JSON 문자열

        Returns:
            파싱된 이벤트 객체 또는 None
        """
        parser = cls.EVENT_PARSERS.get(event_type)
        if not parser:
            logger.warning(f"Unknown event type: {event_type}")
            return None

        try:
            data_dict = json.loads(data)
            return parser(data_dict)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event data: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating event object: {e}")
            return None

    @classmethod
    def parse_raw_sse(cls, raw_line: str) -> tuple:
        """
        원시 SSE 라인 파싱.

        Args:
            raw_line: "event: xxx" 또는 "data: {...}"

        Returns:
            (field_type, value) 튜플
        """
        if ":" not in raw_line:
            return (None, None)

        field_type, value = raw_line.split(":", 1)
        return (field_type.strip(), value.strip())
