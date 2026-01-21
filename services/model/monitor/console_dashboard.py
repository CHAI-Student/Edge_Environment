"""
Console Dashboard for Test Mode.

콘솔 기반 실시간 모니터링 대시보드.

표시 내용:
- Zone별 로드셀 무게
- 최근 이벤트
- Vision Top-5 후보군 (Top/Side)
- 앙상블 결과
- 무게 검증 결과
- 최종 판단 결과
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
import time
import os
import logging

from ..engine.models import JudgmentResult, JudgmentStatus, EnsembleResult
from ..config import ZONE_CHANNEL_MAP

logger = logging.getLogger(__name__)


@dataclass
class ZoneStatus:
    """Zone 상태."""
    zone_id: int
    channel_weights: List[float] = field(default_factory=list)
    total_weight: float = 0.0
    state: str = "STABLE"
    last_delta: float = 0.0
    last_event_time: Optional[float] = None


@dataclass
class VisionResult:
    """Vision 결과."""
    camera_type: str  # "top" or "side"
    camera_id: int
    candidates: List[dict] = field(default_factory=list)


@dataclass
class DashboardState:
    """대시보드 상태."""
    zones: Dict[int, ZoneStatus] = field(default_factory=dict)
    recent_event: Optional[dict] = None
    top_vision: Optional[VisionResult] = None
    side_vision: Optional[VisionResult] = None
    ensemble_result: List[EnsembleResult] = field(default_factory=list)
    weight_validation: Optional[dict] = None
    final_judgment: Optional[JudgmentResult] = None
    last_update: float = 0.0

    def __post_init__(self):
        # 5개 Zone 초기화
        for zone_id in range(5):
            channels = ZONE_CHANNEL_MAP.get(zone_id, [])
            self.zones[zone_id] = ZoneStatus(
                zone_id=zone_id,
                channel_weights=[0.0] * len(channels),
            )


class ConsoleDashboard:
    """
    콘솔 기반 실시간 대시보드.

    --test 모드에서 상품 판단 과정을 시각화합니다.

    Attributes:
        state: 현재 대시보드 상태
        refresh_rate: 화면 갱신 주기 (초)
    """

    BOX_WIDTH = 76

    def __init__(self, refresh_rate: float = 0.5):
        """
        대시보드 초기화.

        Args:
            refresh_rate: 화면 갱신 주기 (초)
        """
        self.state = DashboardState()
        self.refresh_rate = refresh_rate
        self._running = False

    def update_loadcell(self, zone_id: int, weights: List[float], state: str = "STABLE"):
        """
        로드셀 무게 업데이트.

        Args:
            zone_id: Zone ID
            weights: 채널별 무게 리스트
            state: 상태 (STABLE, CHANGING, etc.)
        """
        if zone_id in self.state.zones:
            zone = self.state.zones[zone_id]
            zone.channel_weights = weights
            zone.total_weight = sum(weights)
            zone.state = state
            self.state.last_update = time.time()

    def update_event(self, zone_id: int, delta: float, channels: List[int]):
        """
        이벤트 업데이트.

        Args:
            zone_id: Zone ID
            delta: 무게 변화량
            channels: 변화 감지된 채널
        """
        self.state.recent_event = {
            "zone_id": zone_id,
            "delta": delta,
            "channels": channels,
            "time": time.time(),
        }

        if zone_id in self.state.zones:
            zone = self.state.zones[zone_id]
            zone.last_delta = delta
            zone.last_event_time = time.time()

        self.state.last_update = time.time()

    def update_vision(
        self,
        camera_type: str,
        camera_id: int,
        candidates: List[dict],
    ):
        """
        Vision 결과 업데이트.

        Args:
            camera_type: "top" or "side"
            camera_id: 카메라 ID
            candidates: Top-5 후보군
        """
        result = VisionResult(
            camera_type=camera_type,
            camera_id=camera_id,
            candidates=candidates[:5],  # Top-5
        )

        if camera_type == "top":
            self.state.top_vision = result
        else:
            self.state.side_vision = result

        self.state.last_update = time.time()

    def update_ensemble(self, results: List[EnsembleResult]):
        """
        앙상블 결과 업데이트.

        Args:
            results: EnsembleResult 리스트
        """
        self.state.ensemble_result = results[:5]  # Top-5
        self.state.last_update = time.time()

    def update_weight_validation(
        self,
        product_name: str,
        count: int,
        expected: float,
        actual: float,
        error: float,
        validated: bool,
    ):
        """
        무게 검증 결과 업데이트.

        Args:
            product_name: 상품명
            count: 개수
            expected: 예상 무게
            actual: 실제 무게
            error: 오차
            validated: 검증 통과 여부
        """
        self.state.weight_validation = {
            "product_name": product_name,
            "count": count,
            "expected": expected,
            "actual": actual,
            "error": error,
            "validated": validated,
        }
        self.state.last_update = time.time()

    def update_judgment(self, result: JudgmentResult):
        """
        최종 판단 결과 업데이트.

        Args:
            result: JudgmentResult 인스턴스
        """
        self.state.final_judgment = result
        self.state.last_update = time.time()

    def render(self) -> str:
        """
        대시보드 렌더링.

        Returns:
            렌더링된 문자열
        """
        lines = []

        # 헤더
        lines.append(self._box_top())
        lines.append(self._box_line("MODEL SERVICE - TEST MODE", center=True))
        lines.append(self._box_line(f"Time: {self._format_time(time.time())}", center=True))
        lines.append(self._box_separator())

        # 로드셀 무게
        lines.append(self._box_line(""))
        lines.append(self._box_line("[LoadCell Weights]"))
        for zone_id in range(5):
            zone = self.state.zones.get(zone_id)
            if zone:
                channels = ZONE_CHANNEL_MAP.get(zone_id, [])
                if len(zone.channel_weights) >= 2:
                    ch_str = f"Ch{channels[0]}: {zone.channel_weights[0]:.0f}g, Ch{channels[1]}: {zone.channel_weights[1]:.0f}g"
                else:
                    ch_str = "N/A"
                line = f"Zone {zone_id}: {zone.total_weight:.0f}g ({ch_str}) - {zone.state}"
                lines.append(self._box_line(f"  {line}"))

        # 최근 이벤트
        lines.append(self._box_line(""))
        if self.state.recent_event:
            evt = self.state.recent_event
            evt_time = self._format_time(evt["time"])
            lines.append(
                self._box_line(
                    f"[Recent Event] Zone {evt['zone_id']} | Delta: {evt['delta']:.0f}g | Time: {evt_time}"
                )
            )
        else:
            lines.append(self._box_line("[Recent Event] None"))

        # Vision - Top Camera
        lines.append(self._box_line(""))
        if self.state.top_vision:
            tv = self.state.top_vision
            lines.append(self._box_line(f"[Vision - Top Camera (CAM {tv.camera_id})]"))
            for i, c in enumerate(tv.candidates, 1):
                name = c.get("name", c.get("class_name", "unknown"))
                conf = c.get("confidence", c.get("combined_confidence", 0))
                lines.append(self._box_line(f"  {i}. {name:20s} conf={conf:.3f}"))
        else:
            lines.append(self._box_line("[Vision - Top Camera] No data"))

        # Vision - Side Camera
        lines.append(self._box_line(""))
        if self.state.side_vision:
            sv = self.state.side_vision
            zone_id = sv.camera_id - 1 if sv.camera_id > 0 else 0
            lines.append(self._box_line(f"[Vision - Side Camera (Zone {zone_id}, CAM {sv.camera_id})]"))
            for i, c in enumerate(sv.candidates, 1):
                name = c.get("name", c.get("class_name", "unknown"))
                conf = c.get("confidence", c.get("combined_confidence", 0))
                lines.append(self._box_line(f"  {i}. {name:20s} conf={conf:.3f}"))
        else:
            lines.append(self._box_line("[Vision - Side Camera] No data"))

        # 앙상블 결과
        lines.append(self._box_line(""))
        if self.state.ensemble_result:
            lines.append(self._box_line("[Ensemble Result]"))
            for i, r in enumerate(self.state.ensemble_result, 1):
                status = "CONSENSUS" if r.is_consensus else "TOP_ONLY" if r.top_confidence > 0 else "SIDE_ONLY"
                star = " *" if r.is_consensus else ""
                lines.append(
                    self._box_line(
                        f"  {i}. {r.class_name:20s} combined={r.combined_confidence:.3f} {status}{star}"
                    )
                )
        else:
            lines.append(self._box_line("[Ensemble Result] No data"))

        # 무게 검증
        lines.append(self._box_line(""))
        if self.state.weight_validation:
            wv = self.state.weight_validation
            lines.append(self._box_line("[Weight Validation]"))
            lines.append(
                self._box_line(f"  {wv['product_name']} x {wv['count']} = {wv['expected']:.0f}g")
            )
            check = "VALIDATED" if wv["validated"] else "FAILED"
            check_mark = "+" if wv["validated"] else "-"
            lines.append(
                self._box_line(
                    f"  Expected: {wv['expected']:.0f}g | Actual: {wv['actual']:.0f}g | "
                    f"Error: {wv['error']:.0f}g | {check_mark} {check}"
                )
            )
        else:
            lines.append(self._box_line("[Weight Validation] No data"))

        # 최종 판단
        lines.append(self._box_line(""))
        if self.state.final_judgment:
            fj = self.state.final_judgment
            lines.append(self._box_line("[Final Judgment]"))

            if fj.products:
                for p in fj.products:
                    lines.append(self._box_line(f"  Product: {p.name}"))
                    lines.append(self._box_line(f"  Count: {p.count}"))
                    lines.append(self._box_line(f"  Price: {p.total_price:,}won"))
            else:
                lines.append(self._box_line("  Product: None"))

            lines.append(self._box_line(f"  Status: {fj.status.value.upper()}"))
            lines.append(self._box_line(f"  Confidence: {fj.confidence:.2f}"))
        else:
            lines.append(self._box_line("[Final Judgment] No data"))

        lines.append(self._box_line(""))
        lines.append(self._box_bottom())

        return "\n".join(lines)

    def display(self):
        """화면에 대시보드 출력."""
        # 화면 지우기
        os.system("cls" if os.name == "nt" else "clear")

        # 렌더링 출력
        print(self.render())

    def _box_top(self) -> str:
        """상단 박스 라인."""
        return "+" + "=" * (self.BOX_WIDTH - 2) + "+"

    def _box_bottom(self) -> str:
        """하단 박스 라인."""
        return "+" + "=" * (self.BOX_WIDTH - 2) + "+"

    def _box_separator(self) -> str:
        """구분선."""
        return "+" + "-" * (self.BOX_WIDTH - 2) + "+"

    def _box_line(self, text: str, center: bool = False) -> str:
        """박스 안의 텍스트 라인."""
        content_width = self.BOX_WIDTH - 4  # "| " 와 " |"

        if center:
            text = text.center(content_width)
        else:
            text = text.ljust(content_width)

        # 너무 긴 경우 자르기
        if len(text) > content_width:
            text = text[:content_width]

        return "| " + text + " |"

    def _format_time(self, timestamp: float) -> str:
        """타임스탬프를 시간 문자열로 변환."""
        import datetime
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
