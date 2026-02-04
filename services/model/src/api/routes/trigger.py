"""
Trigger API Routes (v4.4).

POST /trigger - Camera에서 녹화 완료 시 호출
즉시 YOLO 추론 실행 후 결과를 SessionStore에 저장.

v4.4 변경사항:
- TriggerService 사용: ActiveProductStore, PendingTriggerStore 연동
- YOLO classes 파라미터로 사전 필터링 적용
- products 없으면 pending 처리

v4.3 변경사항:
- add_trigger_with_global 사용: GlobalSession 연동 지원

v4.2 변경사항:
- YOLO 추론 비동기화 (asyncio.to_thread)
- 다른 요청과 병렬 처리 가능

사용 흐름:
1. Camera Driver가 녹화 완료 후 /trigger 호출
2. products 확인 (없으면 pending 처리)
3. Model 서비스가 YOLO 추론 실행 (allowed_class_ids 적용)
4. 결과를 SessionStore에 저장
5. DoorSessionStore에 결과 추가 (GlobalSession 연동)
6. session_id 반환
7. Node.js가 /api/judge/multi-zone으로 결과 폴링
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from video import VideoProcessor, VoteResult
from engine import ProductDecisionEngine, EnsembleResult
from session import SessionStore, SessionData, ProductResult, DoorSessionStore, TriggerResult
from session.session_store import generate_session_id
from service.trigger_service import TriggerService, TriggerInput, TriggerOutput, LoadcellReading
from api.deps import (
    get_decision_engine,
    get_video_processor,
    get_session_store,
    get_active_product_store_optional,
    get_door_session_store_optional,
    get_trigger_service_optional,
)
from session.active_product_store import ActiveProductStore
from core.exceptions import (
    VideoProcessingError,
    VideoCorruptedError,
    FFmpegError,
    YOLOInferenceError,
    YOLOModelNotLoadedError,
    YOLOGPUError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trigger"])


# ============================================================================
# Request/Response Models
# ============================================================================


class LoadcellData(BaseModel):
    """로드셀 개별 데이터."""

    timestamp: str = Field(..., description="타임스탬프 (ISO 형식)")
    raw_value: List[str] = Field(..., description="원시 값 리스트 (예: ['+12345', '+12345'])")
    filtered_value: List[str] = Field(..., description="필터링된 값 리스트")
    filter_method: str = Field(default="none", description="필터 방식")


class VideosPaths(BaseModel):
    """비디오 파일 경로."""

    top: Optional[str] = Field(None, description="Top 카메라 AVI 경로")
    side: Optional[str] = Field(None, description="Side 카메라 AVI 경로")


class TriggerRequest(BaseModel):
    """
    트리거 요청 (Camera → Model).

    Camera에서 AVI 파일 녹화 완료 후 호출됩니다.
    """

    zone: int = Field(..., ge=0, description="Zone 번호")
    loadcells: List[LoadcellData] = Field(
        default_factory=list,
        description="로드셀 데이터 목록 (시작~종료)",
    )
    videos: VideosPaths = Field(..., description="비디오 파일 경로")


class TriggerResponse(BaseModel):
    """트리거 응답."""

    success: bool
    session_id: str
    door_session_id: Optional[str] = None
    message: str
    status: str = "complete"  # "complete" or "pending"
    waiting_for: Optional[str] = None  # "products" if pending


# ============================================================================
# Helper Functions
# ============================================================================


def _parse_loadcell_value(value: str) -> float:
    """로드셀 값 파싱 (+12345 형식)."""
    try:
        # +/- 기호 처리
        cleaned = value.strip()
        if cleaned.startswith("+"):
            return float(cleaned[1:])
        return float(cleaned)
    except (ValueError, AttributeError):
        return 0.0


def _detect_stable_regions(
    loadcells: List[LoadcellData],
    window_size: int = 5,
    stability_threshold: float = 15.0,
) -> Tuple[float, float, bool]:
    """
    Loadcell 데이터에서 안정 구간을 감지하고 시작/종료 평균값 계산.

    알고리즘:
    1. 시작부터 sliding window로 std 계산 → 안정 구간 시작점 찾기
    2. 끝에서부터 sliding window로 std 계산 → 안정 구간 종료점 찾기
    3. 각 안정 구간의 평균값 계산

    Args:
        loadcells: 로드셀 데이터 리스트 (시간순)
        window_size: 안정 판단 윈도우 크기
        stability_threshold: 안정으로 판단할 표준편차 임계값 (g)

    Returns:
        (start_avg, end_avg, is_valid): 시작/종료 안정값, 유효성
    """
    if len(loadcells) < window_size * 2:
        return _simple_delta_values(loadcells)

    # filtered_value 추출 (첫 번째 채널 사용)
    values = []
    for lc in loadcells:
        if lc.filtered_value:
            val = _parse_loadcell_value(lc.filtered_value[0])
            values.append(val)

    if len(values) < window_size * 2:
        return _simple_delta_values(loadcells)

    values_arr = np.array(values)

    # 1. 시작 안정 구간 찾기 (앞에서부터)
    start_stable_idx = 0
    for i in range(len(values_arr) - window_size):
        window = values_arr[i:i + window_size]
        if np.std(window) < stability_threshold:
            start_stable_idx = i
            break

    # 시작 안정 구간의 평균
    start_region = values_arr[start_stable_idx:start_stable_idx + window_size]
    start_avg = float(np.mean(start_region))

    # 2. 종료 안정 구간 찾기 (뒤에서부터)
    end_stable_idx = len(values_arr) - window_size
    for i in range(len(values_arr) - 1, window_size - 1, -1):
        window = values_arr[i - window_size + 1:i + 1]
        if np.std(window) < stability_threshold:
            end_stable_idx = i - window_size + 1
            break

    # 종료 안정 구간의 평균
    end_region = values_arr[end_stable_idx:end_stable_idx + window_size]
    end_avg = float(np.mean(end_region))

    # 3. 유효성 검증: 시작과 종료 구간이 겹치면 변화가 없는 것
    is_valid = (end_stable_idx > start_stable_idx + window_size)

    logger.debug(
        f"Stable regions: start_idx={start_stable_idx}, end_idx={end_stable_idx}, "
        f"start_avg={start_avg:.1f}, end_avg={end_avg:.1f}, valid={is_valid}"
    )

    return start_avg, end_avg, is_valid


def _simple_delta_values(loadcells: List[LoadcellData]) -> Tuple[float, float, bool]:
    """단순 첫/마지막 값 비교 (fallback)."""
    if not loadcells:
        return 0.0, 0.0, False

    try:
        start_val = loadcells[0].filtered_value[0] if loadcells[0].filtered_value else "0"
        end_val = loadcells[-1].filtered_value[0] if loadcells[-1].filtered_value else "0"
        start = _parse_loadcell_value(start_val)
        end = _parse_loadcell_value(end_val)
        return start, end, True
    except (IndexError, AttributeError):
        return 0.0, 0.0, False


def _calculate_weight_delta(loadcells: List[LoadcellData]) -> float:
    """
    로드셀 데이터에서 무게 변화량 계산 (안정 구간 기반).

    Args:
        loadcells: 로드셀 데이터 리스트

    Returns:
        무게 변화량 (g) - 음수면 제거, 양수면 추가
    """
    if not loadcells or len(loadcells) < 2:
        return 0.0

    start_avg, end_avg, is_valid = _detect_stable_regions(loadcells)

    if not is_valid:
        logger.warning("Could not detect stable regions, using simple delta")
        try:
            start_val = loadcells[0].filtered_value[0] if loadcells[0].filtered_value else "0"
            end_val = loadcells[-1].filtered_value[0] if loadcells[-1].filtered_value else "0"
            start = _parse_loadcell_value(start_val)
            end = _parse_loadcell_value(end_val)
            delta = end - start
            logger.debug(f"Simple weight delta: start={start}, end={end}, delta={delta}")
            return delta
        except (IndexError, AttributeError) as e:
            logger.warning(f"Failed to calculate weight delta: {e}")
            return 0.0

    delta = end_avg - start_avg
    logger.info(
        f"Weight delta (stable regions): "
        f"start={start_avg:.1f}g -> end={end_avg:.1f}g = {delta:.1f}g"
    )

    return delta


def _vote_results_to_ensemble(
    vote_results: List[VoteResult],
) -> List[EnsembleResult]:
    """
    VoteResult를 EnsembleResult로 변환 (가중치 이미 적용됨).

    Args:
        vote_results: 투표 결과 리스트 (weighted_confidence 포함)

    Returns:
        EnsembleResult 리스트 (기존 판단 엔진과 호환)
    """
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


def _validate_video_paths(videos: VideosPaths) -> None:
    """
    비디오 파일 경로 유효성 검증.

    Args:
        videos: 비디오 파일 경로

    Raises:
        HTTPException: 파일이 존재하지 않는 경우
    """
    if videos.top and not Path(videos.top).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Top video file not found: {videos.top}",
        )

    if videos.side and not Path(videos.side).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Side video file not found: {videos.side}",
        )

    if not videos.top and not videos.side:
        raise HTTPException(
            status_code=400,
            detail="At least one video path (top or side) is required",
        )


# ============================================================================
# Trigger Endpoint
# ============================================================================


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_judgment(
    request: TriggerRequest,
    video_processor: VideoProcessor = Depends(get_video_processor),
    engine: ProductDecisionEngine = Depends(get_decision_engine),
    session_store: SessionStore = Depends(get_session_store),
    active_product_store: ActiveProductStore | None = Depends(get_active_product_store_optional),
    door_session_store: DoorSessionStore | None = Depends(get_door_session_store_optional),
    trigger_service: TriggerService | None = Depends(get_trigger_service_optional),
):
    """
    Camera에서 녹화 완료 시 호출되는 트리거 API (v4.4).

    v4.4: TriggerService를 통한 처리
    1. products 확인 (없으면 pending 처리)
    2. 비디오 파일 경로 검증
    3. YOLO 추론 (allowed_class_ids 적용)
    4. 최종 상품 판단
    5. SessionStore, DoorSessionStore에 저장
    6. session_id 반환

    Args:
        request: 트리거 요청
        trigger_service: TriggerService 의존성 (v4.4)

    Returns:
        TriggerResponse: session_id, door_session_id, status 포함
    """
    start_time = time.time()

    # 세션 ID (로깅용)
    session_id = generate_session_id(request.zone)

    logger.info(f"[TRIGGER] ========== 추론 시작 ==========")
    logger.info(f"[TRIGGER] zone={request.zone}, session_id={session_id}")
    logger.info(f"[TRIGGER] videos: top={request.videos.top}, side={request.videos.side}")
    logger.info(f"[TRIGGER] loadcells: {len(request.loadcells)}개")

    try:
        # v4.4: TriggerService 사용
        if trigger_service is not None:
            # TriggerInput 생성
            loadcells = [
                LoadcellReading(
                    timestamp=lc.timestamp,
                    raw_value=lc.raw_value,
                    filtered_value=lc.filtered_value,
                    filter_method=lc.filter_method,
                )
                for lc in request.loadcells
            ]

            trigger_input = TriggerInput(
                zone=request.zone,
                loadcells=loadcells,
                top_video_path=request.videos.top,
                side_video_path=request.videos.side,
            )

            # TriggerService로 처리 위임 (v4.10: 큐 기반 순차 처리)
            output: TriggerOutput = await trigger_service.enqueue_trigger(trigger_input)

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"[TRIGGER] TriggerService 완료: elapsed={elapsed_ms:.1f}ms")

            # v4.5: 에러 응답 처리 - success=False면 HTTP 400 반환
            if not output.success:
                logger.error(
                    f"[TRIGGER ERROR] session_id={output.session_id}, "
                    f"error_code={output.error_code}, message={output.message}"
                )
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": output.error_code or "TRIGGER_ERROR",
                        "message": output.message,
                        "session_id": output.session_id,
                    },
                )

            return TriggerResponse(
                success=output.success,
                session_id=output.session_id,
                door_session_id=output.door_session_id,
                message=output.message,
                status=output.status,
                waiting_for=output.waiting_for,
            )

        # Fallback: TriggerService가 없으면 기존 로직 실행
        logger.warning("[TRIGGER] TriggerService not available, using fallback logic")

        # 1. 비디오 파일 경로 검증
        _validate_video_paths(request.videos)

        # 세션 초기 저장 (processing 상태로)
        initial_session = SessionData(
            session_id=session_id,
            zone=request.zone,
            status="processing",
            processing_stage="extracting_frames",
            processing_stage_detail="비디오 프레임 추출 준비 중",
        )
        session_store.save(session_id, initial_session)

        # 2. 비디오 처리 (전체 프레임 YOLO + 투표)
        # 상태 업데이트: 프레임 추출 중
        session_store.update_stage(
            session_id,
            processing_stage="extracting_frames",
            processing_stage_detail="비디오에서 프레임 추출 중",
        )

        # v4.2: 비동기 실행으로 다른 요청과 병렬 처리 가능
        processing_result = await asyncio.to_thread(
            video_processor.process_videos,
            top_path=request.videos.top,
            side_path=request.videos.side,
        )

        vote_results = processing_result.vote_results
        stats = processing_result.stats

        logger.info(f"[TRIGGER] ========== 비디오 처리 완료 ==========")
        logger.info(
            f"[TRIGGER] 총 프레임: {stats.top_frames + stats.side_frames}, "
            f"후보: {len(vote_results)}개, 처리시간: {stats.processing_time_ms:.1f}ms"
        )
        logger.info(f"[TRIGGER] Top-5 후보군:")
        for i, v in enumerate(vote_results[:5]):
            logger.info(
                f"  [{i+1}] {v.class_name}: votes={v.vote_count}, "
                f"weighted_conf={v.weighted_confidence:.3f}, "
                f"top={v.top_detected}, side={v.side_detected}"
            )

        # 상태 업데이트: 상품 후보 도출 완료, 개수 판단 중
        session_store.update_stage(
            session_id,
            processing_stage="calculating_count",
            processing_stage_detail=f"후보 {len(vote_results)}개 도출, 개수 판단 중",
        )

        # 3. 로드셀 데이터에서 무게 변화량 계산
        delta_weight = _calculate_weight_delta(request.loadcells)
        logger.info(f"[TRIGGER] ========== 무게 계산 ==========")
        logger.info(f"[TRIGGER] delta_weight={delta_weight:.1f}g")

        # 4. 투표 결과를 EnsembleResult로 변환
        vision_candidates = _vote_results_to_ensemble(vote_results)

        # 5. 최종 상품 판단
        vision_only = delta_weight == 0.0 and len(request.loadcells) == 0

        result = engine.judge(
            vision_candidates=vision_candidates,
            delta_weight=delta_weight,
            vision_only=vision_only,
        )

        # 6. SessionStore에 결과 저장
        # YOLO class_id → IF11 product_idx 조회
        def get_product_idx(product_id: int) -> str | None:
            """YOLO class_id로 IF11 product_idx 조회."""
            if active_product_store is None:
                return None
            product_info = active_product_store.get_by_yolo_class_id(product_id)
            if product_info and product_info.product_idx:
                return product_info.product_idx
            return None

        products = [
            ProductResult(
                product_id=p.product_id,
                product_idx=get_product_idx(p.product_id),
                name=p.name,
                count=p.count,
                price=p.unit_price,
                confidence=p.confidence,
            )
            for p in result.products
        ]

        # vision_candidates를 dict로 변환 (재계산용)
        vision_candidates_dicts = [
            vc.to_dict() for vc in vision_candidates
        ]

        session_data = SessionData(
            session_id=session_id,
            zone=request.zone,
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

        session_store.save(session_id, session_data)

        # 7. DoorSessionStore에 trigger 결과 추가 (v4.3: GlobalSession 연동)
        door_session = None
        if door_session_store is not None:
            elapsed_ms_for_trigger = (time.time() - start_time) * 1000
            trigger_result = TriggerResult(
                trigger_id="",  # DoorSessionStore에서 자동 할당
                session_id=session_id,
                timestamp=time.time(),
                products=products,
                delta_weight=delta_weight,
                confidence=result.confidence,
                video_paths={
                    "top": str(request.videos.top) if request.videos.top else "",
                    "side": str(request.videos.side) if request.videos.side else "",
                },
                is_return=delta_weight > 0,
                processing_time_ms=elapsed_ms_for_trigger,
            )
            # v4.3: add_trigger_with_global 사용 (GlobalSession 연동)
            door_session = door_session_store.add_trigger_with_global(
                zone=request.zone,
                result=trigger_result,
            )
            # GlobalSession 활성 여부 로깅
            is_global_active = door_session_store.is_global_session_active()
            logger.info(
                f"[TRIGGER] Door session: {door_session.door_session_id}, "
                f"triggers={door_session.trigger_count}, "
                f"aggregated_products={len(door_session.aggregated_products)}, "
                f"global_session_active={is_global_active}"
            )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"[TRIGGER] ========== 판단 결과 ==========")
        logger.info(f"[TRIGGER] status={result.status.value}, confidence={result.confidence:.3f}")
        for p in result.products:
            logger.info(f"  - {p.name} x{p.count}: {p.total_price}원")
        logger.info(f"[TRIGGER] total_price={result.total_price}원, elapsed={elapsed_ms:.1f}ms")

        return TriggerResponse(
            success=True,
            session_id=session_id,
            door_session_id=door_session.door_session_id if door_session else None,
            message="추론 완료",
            status="complete",
        )

    except HTTPException as e:
        logger.error(
            f"[TRIGGER ERROR] session_id={session_id}, "
            f"status={e.status_code}, detail={e.detail}"
        )
        session_store.update_stage(
            session_id,
            processing_stage="error",
            processing_stage_detail=f"HTTP 오류: {e.status_code}",
        )
        raise

    except FileNotFoundError as e:
        logger.error(f"[TRIGGER ERROR] session_id={session_id}, video file not found: {e}")
        session_store.update_stage(
            session_id,
            processing_stage="error",
            processing_stage_detail=f"비디오 파일 없음: {e}",
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "VIDEO_FILE_NOT_FOUND",
                "message": f"Video file not found: {e}",
            },
        )

    except (VideoCorruptedError, FFmpegError) as e:
        logger.error(f"[TRIGGER ERROR] session_id={session_id}, video processing: {e}", exc_info=True)
        session_store.update_stage(
            session_id,
            processing_stage="error",
            processing_stage_detail=f"비디오 처리 오류: {e.error_code}",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": e.error_code,
                "message": str(e),
                "video_path": getattr(e, "video_path", None),
            },
        )

    except VideoProcessingError as e:
        logger.error(f"[TRIGGER ERROR] session_id={session_id}, video processing: {e}", exc_info=True)
        session_store.update_stage(
            session_id,
            processing_stage="error",
            processing_stage_detail=f"비디오 처리 오류: {e.error_code}",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": e.error_code,
                "message": str(e),
            },
        )

    except YOLOModelNotLoadedError as e:
        logger.error(f"[TRIGGER ERROR] session_id={session_id}, YOLO model not loaded: {e}")
        session_store.update_stage(
            session_id,
            processing_stage="error",
            processing_stage_detail="YOLO 모델 미로드",
        )
        raise HTTPException(
            status_code=503,  # Service Unavailable
            detail={
                "error_code": e.error_code,
                "message": "YOLO model not loaded. Service is not ready.",
            },
        )

    except YOLOGPUError as e:
        logger.error(f"[TRIGGER ERROR] session_id={session_id}, YOLO GPU: {e}", exc_info=True)
        session_store.update_stage(
            session_id,
            processing_stage="error",
            processing_stage_detail=f"YOLO GPU 오류: {e.error_code}",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": e.error_code,
                "message": str(e),
            },
        )

    except YOLOInferenceError as e:
        logger.error(f"[TRIGGER ERROR] session_id={session_id}, YOLO inference: {e}", exc_info=True)
        session_store.update_stage(
            session_id,
            processing_stage="error",
            processing_stage_detail=f"YOLO 추론 오류: {e.error_code}",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": e.error_code,
                "message": str(e),
            },
        )

    except Exception as e:
        logger.error(f"[TRIGGER ERROR] session_id={session_id}, unexpected: {e}", exc_info=True)
        session_store.update_stage(
            session_id,
            processing_stage="error",
            processing_stage_detail=f"내부 오류: {type(e).__name__}",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERNAL_ERROR",
                "message": f"Internal server error: {type(e).__name__}: {str(e)}",
            },
        )


# ============================================================================
# Stats Endpoint
# ============================================================================


@router.get("/trigger/stats")
async def get_trigger_stats(
    video_processor: VideoProcessor = Depends(get_video_processor),
    session_store: SessionStore = Depends(get_session_store),
):
    """
    트리거 및 세션 상태 조회.

    Returns:
        프로세서 설정 및 세션 통계
    """
    return {
        "video_processor": {
            "min_vote_ratio": video_processor.min_vote_ratio,
            "confidence_threshold": video_processor.confidence_threshold,
            "yolo_loaded": video_processor.yolo.is_loaded,
        },
        "session_store": session_store.get_stats(),
        "timestamp": time.time(),
    }
