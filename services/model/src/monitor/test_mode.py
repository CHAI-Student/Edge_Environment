"""
Test Mode Handler.

DEPRECATED: 이 모듈은 더 이상 사용되지 않습니다.

이전에는 Model 서비스가 io_board SSE를 직접 구독했으나,
현재 아키텍처에서는 Node.js Orchestrator가 SSE를 구독하고
Model 서비스를 stateless하게 호출합니다.

테스트는 Node.js 대시보드(http://localhost:8889/dashboard.html)를 통해 수행하세요.
"""

import asyncio
import logging
import warnings
from typing import Optional

warnings.warn(
    "test_mode.py is deprecated. Model service is now stateless. "
    "Use Node.js dashboard for testing.",
    DeprecationWarning,
    stacklevel=2,
)

from .console_dashboard import ConsoleDashboard
# NOTE: sse_client module removed - Model is now stateless
# from ..sse_client import IOBoardSubscriber, LoadcellChangeEvent, LoadcellUpdateEvent
# from ..sse_client.zone_detector import ZoneDetector
from camera import FrameCapturer
from vision import YOLOWrapper, HandProximityFilter, Top5Extractor, MultiViewEnsemble
from engine import ProductDecisionEngine, EventTracker
from database.product_db import ProductDatabase
from api.node_client import NodeJSClient
from config import config, ZONE_CHANNEL_MAP, ZONE_CAMERA_MAP, TOP_CAMERA_ID

logger = logging.getLogger(__name__)


# Placeholder types for removed sse_client module
class IOBoardSubscriber:
    """Placeholder - SSE subscription moved to Node.js Orchestrator."""
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "IOBoardSubscriber removed. Model is now stateless. "
            "SSE subscription is handled by Node.js Orchestrator."
        )


class LoadcellChangeEvent:
    """Placeholder for removed event type."""
    pass


class LoadcellUpdateEvent:
    """Placeholder for removed event type."""
    pass


class ZoneDetector:
    """Placeholder - Zone detection moved to Node.js."""
    def __init__(self):
        raise NotImplementedError(
            "ZoneDetector removed. Zone detection is handled by Node.js Orchestrator."
        )


class TestModeHandler:
    """
    --test 모드 핸들러.

    SSE 이벤트를 수신하고 실시간으로 상품 판단을 수행하며
    콘솔 대시보드에 결과를 표시합니다.

    Attributes:
        dashboard: 콘솔 대시보드
        subscriber: io_board SSE 구독자
        zone_detector: Zone 감지기
        frame_capturer: 프레임 캡처러
        yolo_wrapper: YOLO 추론 래퍼
        hand_filter: 손 근접 필터
        top5_extractor: Top-5 추출기
        ensemble: Multi-View 앙상블
        decision_engine: 판단 엔진
        event_tracker: 이벤트 트래커
        node_client: Node.js 클라이언트
    """

    def __init__(
        self,
        io_board_url: str = None,
        camera_driver_url: str = None,
        node_js_url: str = None,
        yolo_model_path: str = None,
        refresh_rate: float = 0.5,
    ):
        """
        핸들러 초기화.

        DEPRECATED: 이 클래스는 더 이상 사용되지 않습니다.
        Model 서비스는 이제 stateless하며, SSE 구독은 Node.js가 담당합니다.

        Args:
            io_board_url: io_board 서비스 URL (DEPRECATED)
            camera_driver_url: camera_driver 서비스 URL (DEPRECATED)
            node_js_url: Node.js 오케스트레이터 URL
            yolo_model_path: YOLO 모델 경로
            refresh_rate: 대시보드 갱신 주기
        """
        # DEPRECATED: io_board_url, camera_driver_url은 더 이상 config에 없음
        self.io_board_url = io_board_url or "http://localhost:8000"
        self.camera_driver_url = camera_driver_url or "http://localhost:8003"
        self.node_js_url = node_js_url or config.nodejs_url
        self.yolo_model_path = yolo_model_path or config.yolo_model_path

        # 대시보드
        self.dashboard = ConsoleDashboard(refresh_rate=refresh_rate)

        # Zone 감지기
        self.zone_detector = ZoneDetector()

        # 컴포넌트 (lazy 초기화)
        self._subscriber: Optional[IOBoardSubscriber] = None
        self._frame_capturer: Optional[FrameCapturer] = None
        self._yolo_wrapper: Optional[YOLOWrapper] = None
        self._hand_filter: Optional[HandProximityFilter] = None
        self._top5_extractor: Optional[Top5Extractor] = None
        self._ensemble: Optional[MultiViewEnsemble] = None
        self._product_db: Optional[ProductDatabase] = None
        self._decision_engine: Optional[ProductDecisionEngine] = None
        self._event_tracker: Optional[EventTracker] = None
        self._node_client: Optional[NodeJSClient] = None

        # 제어 플래그
        self._running = False
        self._display_task: Optional[asyncio.Task] = None

    async def start(self):
        """테스트 모드 시작."""
        logger.info("Starting test mode...")

        # 컴포넌트 초기화
        await self._init_components()

        # SSE 구독 시작
        self._subscriber = IOBoardSubscriber(
            base_url=self.io_board_url,
            on_change=self._on_loadcell_change,
            on_update=self._on_loadcell_update,
        )

        self._running = True

        # 대시보드 갱신 태스크
        self._display_task = asyncio.create_task(self._display_loop())

        # SSE 스트림 시작
        await self._subscriber.start()

    async def stop(self):
        """테스트 모드 종료."""
        logger.info("Stopping test mode...")

        self._running = False

        if self._subscriber:
            await self._subscriber.stop()

        if self._display_task:
            self._display_task.cancel()
            try:
                await self._display_task
            except asyncio.CancelledError:
                pass

        if self._node_client:
            await self._node_client.stop()

        logger.info("Test mode stopped")

    async def _init_components(self):
        """컴포넌트 초기화."""
        # Frame Capturer
        self._frame_capturer = FrameCapturer(base_url=self.camera_driver_url)

        # Vision 파이프라인
        try:
            self._yolo_wrapper = YOLOWrapper(model_path=self.yolo_model_path)
        except Exception as e:
            logger.warning(f"Failed to load YOLO model: {e}, using dummy mode")
            self._yolo_wrapper = None

        self._hand_filter = HandProximityFilter()
        self._top5_extractor = Top5Extractor()
        self._ensemble = MultiViewEnsemble()

        # 판단 엔진
        self._product_db = ProductDatabase()
        self._decision_engine = ProductDecisionEngine(product_db=self._product_db)
        self._event_tracker = EventTracker()

        # Node.js 클라이언트
        self._node_client = NodeJSClient(base_url=self.node_js_url)

        logger.info("Test mode components initialized")

    async def _on_loadcell_update(self, event: LoadcellUpdateEvent):
        """
        로드셀 업데이트 이벤트 핸들러.

        Args:
            event: LoadcellUpdateEvent
        """
        # 각 Zone별 무게 업데이트
        for zone_id in range(5):
            channels = ZONE_CHANNEL_MAP.get(zone_id, [])
            weights = []

            for ch in channels:
                if ch < len(event.filtered_values):
                    weights.append(event.filtered_values[ch])
                else:
                    weights.append(0.0)

            self.dashboard.update_loadcell(zone_id, weights, state="STABLE")

    async def _on_loadcell_change(self, event: LoadcellChangeEvent):
        """
        로드셀 변화 이벤트 핸들러.

        무게 변화 감지 시 Vision + Weight 판단을 수행합니다.

        Args:
            event: LoadcellChangeEvent
        """
        # Zone 감지
        zone_info = self.zone_detector.get_primary_zone(
            changed_indices=event.changed_indices,
            old_values=event.old_values,
            new_values=event.new_values,
        )

        if zone_info is None:
            logger.debug("No zone detected for loadcell change")
            return

        zone_id = zone_info.zone_id
        delta_weight = zone_info.delta_weight

        logger.info(f"Zone {zone_id} change detected: delta={delta_weight:.1f}g")

        # 대시보드 이벤트 업데이트
        self.dashboard.update_event(zone_id, delta_weight, event.changed_indices)

        # Zone 상태 업데이트
        channels = ZONE_CHANNEL_MAP.get(zone_id, [])
        weights = [
            event.new_values[ch] if ch < len(event.new_values) else 0.0
            for ch in channels
        ]
        self.dashboard.update_loadcell(zone_id, weights, state="CHANGING")

        # 이벤트 트래커 업데이트
        self._event_tracker.on_weight_change(zone_id, delta_weight)

        # Vision 추론 수행
        try:
            await self._process_vision_and_judgment(zone_id, delta_weight)
        except Exception as e:
            logger.error(f"Error processing vision/judgment: {e}", exc_info=True)

    async def _process_vision_and_judgment(self, zone_id: int, delta_weight: float):
        """
        Vision 추론 및 상품 판단 수행.

        Args:
            zone_id: Zone ID
            delta_weight: 무게 변화량
        """
        # 1. 프레임 캡처
        captured = await self._frame_capturer.capture_zone(zone_id)

        top_candidates = []
        side_candidates = []

        # 2. Vision 추론 (YOLO가 로드된 경우)
        if self._yolo_wrapper and captured.top_frame is not None:
            # Top Camera
            top_detections = self._yolo_wrapper.detect(captured.top_frame)
            top_filtered = self._hand_filter.filter(top_detections)
            top_result = self._top5_extractor.extract(top_filtered.products)
            top_candidates = top_result.candidates

            # 대시보드 업데이트
            self.dashboard.update_vision(
                camera_type="top",
                camera_id=TOP_CAMERA_ID,
                candidates=[
                    {"name": c.name, "confidence": c.conf}
                    for c in top_candidates
                ],
            )

        if self._yolo_wrapper and captured.side_frame is not None:
            # Side Camera
            side_detections = self._yolo_wrapper.detect(captured.side_frame)
            side_filtered = self._hand_filter.filter(side_detections)
            side_result = self._top5_extractor.extract(side_filtered.products)
            side_candidates = side_result.candidates

            # 대시보드 업데이트
            self.dashboard.update_vision(
                camera_type="side",
                camera_id=ZONE_CAMERA_MAP.get(zone_id, 1),
                candidates=[
                    {"name": c.name, "confidence": c.conf}
                    for c in side_candidates
                ],
            )

        # 3. Multi-View Ensemble
        ensemble_results = self._ensemble.ensemble(top_candidates, side_candidates)
        self.dashboard.update_ensemble(ensemble_results)

        # 4. 상품 판단
        judgment = self._decision_engine.judge(
            vision_candidates=ensemble_results,
            delta_weight=delta_weight,
        )

        # 5. 대시보드 업데이트
        if judgment.products:
            p = judgment.products[0]
            self.dashboard.update_weight_validation(
                product_name=p.name,
                count=p.count,
                expected=judgment.weight_explained,
                actual=abs(delta_weight),
                error=judgment.weight_residual,
                validated=judgment.status == "complete",
            )

        self.dashboard.update_judgment(judgment)

        # 6. 이벤트 트래커 완료 처리
        self._event_tracker.on_processing_complete(zone_id, judgment.to_node_response())

        # 7. Node.js로 결과 전송
        try:
            await self._node_client.send_judgment(zone_id, judgment)
        except Exception as e:
            logger.warning(f"Failed to send judgment to Node.js: {e}")

        logger.info(
            f"Zone {zone_id} judgment: status={judgment.status.value}, "
            f"products={len(judgment.products)}, price={judgment.total_price}"
        )

    async def _display_loop(self):
        """대시보드 갱신 루프."""
        while self._running:
            try:
                self.dashboard.display()
                await asyncio.sleep(self.dashboard.refresh_rate)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Display error: {e}")
                await asyncio.sleep(1.0)

    async def run(self):
        """테스트 모드 실행 (블로킹)."""
        await self.start()

        try:
            # Ctrl+C 대기
            while self._running:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            await self.stop()
