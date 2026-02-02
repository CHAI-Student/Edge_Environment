"""
Trigger Service (v4.2).

트리거 비즈니스 로직 - YOLO 추론 및 세션 저장.
라우터에서 분리된 핵심 비즈니스 로직.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from video import VideoProcessor, VoteResult
from engine import ProductDecisionEngine, EnsembleResult
from session import SessionStore, SessionData, ProductResult, DoorSessionStore, TriggerResult
from session.session_store import generate_session_id
from database.product_db import ProductDatabase

logger = logging.getLogger(__name__)


@dataclass
class LoadcellReading:
    """로드셀 읽기 데이터."""
    timestamp: str
    raw_value: List[str]
    filtered_value: List[str]
    filter_method: str = "none"


@dataclass
class TriggerInput:
    """트리거 입력 데이터."""
    zone: int
    loadcells: List[LoadcellReading]
    top_video_path: Optional[str]
    side_video_path: Optional[str]


@dataclass
class TriggerOutput:
    """트리거 출력 데이터."""
    success: bool
    session_id: str
    door_session_id: Optional[str]
    message: str
    error_code: Optional[str] = None


class TriggerService:
    """
    트리거 비즈니스 로직 서비스.

    YOLO 추론, 무게 계산, 상품 판단, 세션 저장을 담당.
    """

    def __init__(
        self,
        video_processor: VideoProcessor,
        engine: ProductDecisionEngine,
        session_store: SessionStore,
        product_db: ProductDatabase,
        door_session_store: Optional[DoorSessionStore] = None,
    ):
        """
        Initialize trigger service.

        Args:
            video_processor: VideoProcessor 인스턴스
            engine: ProductDecisionEngine 인스턴스
            session_store: SessionStore 인스턴스
            product_db: ProductDatabase 인스턴스
            door_session_store: DoorSessionStore 인스턴스 (선택)
        """
        self._video_processor = video_processor
        self._engine = engine
        self._session_store = session_store
        self._product_db = product_db
        self._door_session_store = door_session_store

    async def process_trigger(self, input_data: TriggerInput) -> TriggerOutput:
        """
        트리거 요청 처리.

        Args:
            input_data: 트리거 입력 데이터

        Returns:
            TriggerOutput: 처리 결과
        """
        start_time = time.time()
        session_id = generate_session_id(input_data.zone)

        logger.info(f"[TRIGGER] ========== 추론 시작 ==========")
        logger.info(f"[TRIGGER] zone={input_data.zone}, session_id={session_id}")
        logger.info(f"[TRIGGER] videos: top={input_data.top_video_path}, side={input_data.side_video_path}")
        logger.info(f"[TRIGGER] loadcells: {len(input_data.loadcells)}개")

        # 1. 비디오 파일 검증
        validation_error = self._validate_video_paths(
            input_data.top_video_path,
            input_data.side_video_path,
        )
        if validation_error:
            return TriggerOutput(
                success=False,
                session_id=session_id,
                door_session_id=None,
                message=validation_error,
                error_code="VIDEO_VALIDATION_ERROR",
            )

        # 2. 초기 세션 저장 (processing 상태)
        initial_session = SessionData(
            session_id=session_id,
            zone=input_data.zone,
            status="processing",
            processing_stage="extracting_frames",
            processing_stage_detail="비디오 프레임 추출 준비 중",
        )
        self._session_store.save(session_id, initial_session)

        # 3. 비디오 처리 (비동기)
        self._session_store.update_stage(
            session_id,
            processing_stage="extracting_frames",
            processing_stage_detail="비디오에서 프레임 추출 중",
        )

        processing_result = await asyncio.to_thread(
            self._video_processor.process_videos,
            top_path=input_data.top_video_path,
            side_path=input_data.side_video_path,
        )

        vote_results = processing_result.vote_results
        stats = processing_result.stats

        logger.info(f"[TRIGGER] ========== 비디오 처리 완료 ==========")
        logger.info(
            f"[TRIGGER] 총 프레임: {stats.top_frames + stats.side_frames}, "
            f"후보: {len(vote_results)}개, 처리시간: {stats.processing_time_ms:.1f}ms"
        )

        # 4. 처리 단계 업데이트
        self._session_store.update_stage(
            session_id,
            processing_stage="calculating_count",
            processing_stage_detail=f"후보 {len(vote_results)}개 도출, 개수 판단 중",
        )

        # 5. 무게 변화량 계산
        delta_weight = self._calculate_weight_delta(input_data.loadcells)
        logger.info(f"[TRIGGER] ========== 무게 계산 ==========")
        logger.info(f"[TRIGGER] delta_weight={delta_weight:.1f}g")

        # 6. 투표 결과를 EnsembleResult로 변환
        vision_candidates = self._vote_results_to_ensemble(vote_results)

        # 7. 최종 상품 판단
        vision_only = delta_weight == 0.0 and len(input_data.loadcells) == 0
        result = self._engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=delta_weight,
            vision_only=vision_only,
        )

        # 8. SessionStore에 결과 저장
        products = [
            ProductResult(
                product_id=p.product_id,
                product_idx=self._get_product_idx(p.product_id),
                name=p.name,
                count=p.count,
                price=p.unit_price,
                confidence=p.confidence,
            )
            for p in result.products
        ]

        vision_candidates_dicts = [vc.to_dict() for vc in vision_candidates]

        session_data = SessionData(
            session_id=session_id,
            zone=input_data.zone,
            products=products,
            total_price=result.total_price,
            delta_weight=delta_weight,
            status="complete",
            processing_stage="complete",
            processing_stage_detail=f"상품 {len(products)}개 판단 완료",
            confidence=result.confidence,
            top_frames=stats.top_frames,
            side_frames=stats.side_frames,
            processing_time_ms=stats.processing_time_ms,
            vision_candidates=vision_candidates_dicts,
        )
        self._session_store.save(session_id, session_data)

        # 9. DoorSessionStore에 추가 (v4.1)
        door_session_id = None
        if self._door_session_store is not None:
            elapsed_ms = (time.time() - start_time) * 1000
            trigger_result = TriggerResult(
                trigger_id="",
                session_id=session_id,
                timestamp=time.time(),
                products=products,
                delta_weight=delta_weight,
                confidence=result.confidence,
                video_paths={
                    "top": str(input_data.top_video_path) if input_data.top_video_path else "",
                    "side": str(input_data.side_video_path) if input_data.side_video_path else "",
                },
                is_return=delta_weight > 0,
                processing_time_ms=elapsed_ms,
            )
            door_session = self._door_session_store.add_trigger(
                zone=input_data.zone,
                result=trigger_result,
            )
            door_session_id = door_session.door_session_id
            logger.info(
                f"[TRIGGER] Door session: {door_session_id}, "
                f"triggers={door_session.trigger_count}, "
                f"aggregated_products={len(door_session.aggregated_products)}"
            )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"[TRIGGER] ========== 판단 결과 ==========")
        logger.info(f"[TRIGGER] status={result.status.value}, confidence={result.confidence:.3f}")
        for p in result.products:
            logger.info(f"  - {p.name} x{p.count}: {p.total_price}원")
        logger.info(f"[TRIGGER] total_price={result.total_price}원, elapsed={elapsed_ms:.1f}ms")

        return TriggerOutput(
            success=True,
            session_id=session_id,
            door_session_id=door_session_id,
            message="추론 완료",
        )

    def _validate_video_paths(
        self,
        top_path: Optional[str],
        side_path: Optional[str],
    ) -> Optional[str]:
        """비디오 파일 경로 검증."""
        if top_path and not Path(top_path).exists():
            return f"Top video file not found: {top_path}"
        if side_path and not Path(side_path).exists():
            return f"Side video file not found: {side_path}"
        if not top_path and not side_path:
            return "At least one video path (top or side) is required"
        return None

    def _get_product_idx(self, product_id: int) -> Optional[str]:
        """YOLO class_id로 IF11 product_idx 조회."""
        product_info = self._product_db.get_by_yolo_class_id(product_id)
        if product_info and product_info.product_idx:
            return product_info.product_idx
        return None

    def _calculate_weight_delta(self, loadcells: List[LoadcellReading]) -> float:
        """로드셀 데이터에서 무게 변화량 계산."""
        if not loadcells or len(loadcells) < 2:
            return 0.0

        start_avg, end_avg, is_valid = self._detect_stable_regions(loadcells)

        if not is_valid:
            logger.warning("Could not detect stable regions, using simple delta")
            try:
                start_val = loadcells[0].filtered_value[0] if loadcells[0].filtered_value else "0"
                end_val = loadcells[-1].filtered_value[0] if loadcells[-1].filtered_value else "0"
                start = self._parse_loadcell_value(start_val)
                end = self._parse_loadcell_value(end_val)
                return end - start
            except (IndexError, AttributeError) as e:
                logger.warning(f"Failed to calculate weight delta: {e}")
                return 0.0

        delta = end_avg - start_avg
        logger.info(
            f"Weight delta (stable regions): "
            f"start={start_avg:.1f}g -> end={end_avg:.1f}g = {delta:.1f}g"
        )
        return delta

    def _detect_stable_regions(
        self,
        loadcells: List[LoadcellReading],
        window_size: int = 5,
        stability_threshold: float = 15.0,
    ) -> Tuple[float, float, bool]:
        """안정 구간 감지하여 시작/종료 평균값 계산."""
        if len(loadcells) < window_size * 2:
            return self._simple_delta_values(loadcells)

        values = []
        for lc in loadcells:
            if lc.filtered_value:
                val = self._parse_loadcell_value(lc.filtered_value[0])
                values.append(val)

        if len(values) < window_size * 2:
            return self._simple_delta_values(loadcells)

        values_arr = np.array(values)

        # 시작 안정 구간 찾기
        start_stable_idx = 0
        for i in range(len(values_arr) - window_size):
            window = values_arr[i:i + window_size]
            if np.std(window) < stability_threshold:
                start_stable_idx = i
                break

        start_region = values_arr[start_stable_idx:start_stable_idx + window_size]
        start_avg = float(np.mean(start_region))

        # 종료 안정 구간 찾기
        end_stable_idx = len(values_arr) - window_size
        for i in range(len(values_arr) - 1, window_size - 1, -1):
            window = values_arr[i - window_size + 1:i + 1]
            if np.std(window) < stability_threshold:
                end_stable_idx = i - window_size + 1
                break

        end_region = values_arr[end_stable_idx:end_stable_idx + window_size]
        end_avg = float(np.mean(end_region))

        is_valid = (end_stable_idx > start_stable_idx + window_size)

        logger.debug(
            f"Stable regions: start_idx={start_stable_idx}, end_idx={end_stable_idx}, "
            f"start_avg={start_avg:.1f}, end_avg={end_avg:.1f}, valid={is_valid}"
        )

        return start_avg, end_avg, is_valid

    def _simple_delta_values(
        self, loadcells: List[LoadcellReading]
    ) -> Tuple[float, float, bool]:
        """단순 첫/마지막 값 비교 (fallback)."""
        if not loadcells:
            return 0.0, 0.0, False

        try:
            start_val = loadcells[0].filtered_value[0] if loadcells[0].filtered_value else "0"
            end_val = loadcells[-1].filtered_value[0] if loadcells[-1].filtered_value else "0"
            start = self._parse_loadcell_value(start_val)
            end = self._parse_loadcell_value(end_val)
            return start, end, True
        except (IndexError, AttributeError):
            return 0.0, 0.0, False

    def _parse_loadcell_value(self, value: str) -> float:
        """로드셀 값 파싱 (+12345 형식)."""
        try:
            cleaned = value.strip()
            if cleaned.startswith("+"):
                return float(cleaned[1:])
            return float(cleaned)
        except (ValueError, AttributeError):
            return 0.0

    def _vote_results_to_ensemble(
        self, vote_results: List[VoteResult]
    ) -> List[EnsembleResult]:
        """VoteResult를 EnsembleResult로 변환."""
        ensemble_results = []
        for vote in vote_results:
            ensemble = EnsembleResult(
                class_id=vote.class_id,
                class_name=vote.class_name,
                top_confidence=vote.top_max_confidence,
                side_confidence=vote.side_max_confidence,
                combined_confidence=vote.weighted_confidence,
                vote_count=2 if (vote.top_detected and vote.side_detected) else 1,
            )
            ensemble_results.append(ensemble)
        return ensemble_results
