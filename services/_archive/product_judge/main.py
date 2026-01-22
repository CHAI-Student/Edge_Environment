"""
Product Judgment Service - FastAPI Server.

상품 판단 서비스 메인 진입점.

기능:
- POST /api/judge: 실제 상품 판단 (스냅샷 + 로드셀)
- POST /api/test: 테스트용 판단 (YOLO 결과 직접 입력)
- POST /api/simulate: 시뮬레이션 (product_id + count 직접 지정)
- GET /api/health: 헬스 체크
- GET /api/products: 등록된 상품 목록

사용:
    uvicorn product_judge.main:app --host 0.0.0.0 --port 8002

Node.js 연동:
    POST http://localhost:8080/api/test
    {
        "detections": [...],
        "delta_weight": -365.0
    }
"""

import logging
import os
import time
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .interfaces.api_models import (
    JudgeRequest,
    JudgeResponse,
    TestRequest,
    SimulateRequest,
    ProductOutput,
    WeightInfo,
    HealthResponse,
    ErrorResponse,
    JudgmentStatusEnum,
    # Advanced scenario models
    MultiZoneJudgeRequest,
    MultiZoneJudgeResponse,
    MultiZoneResult,
    JudgeWithHistoryRequest,
    JudgeWithHistoryResponse,
    ReturnDetectionResult,
    RecognitionStats,
    CrossZoneMovement as CrossZoneMovementModel,
)
from .engine.models import EnsembleResult, JudgmentStatus
from .engine.decision_engine import ProductDecisionEngine
from .engine.return_detector import ReturnDetector
from .engine.rapid_pickup_handler import RapidPickupHandler
from .database.product_db import ProductDatabase
from .vision.yolo_wrapper import YOLOWrapper, YOLODetection
from .vision.top5_extractor import Top5Extractor
from .vision.multi_hand_detector import MultiHandDetector
from .weight.cross_zone_detector import CrossZoneDetector
from .weight.baseline_manager import BaselineManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 전역 객체
product_db: Optional[ProductDatabase] = None
decision_engine: Optional[ProductDecisionEngine] = None
top5_extractor: Optional[Top5Extractor] = None
multi_hand_detector: Optional[MultiHandDetector] = None
return_detector: Optional[ReturnDetector] = None
cross_zone_detector: Optional[CrossZoneDetector] = None
baseline_manager: Optional[BaselineManager] = None
rapid_pickup_handler: Optional[RapidPickupHandler] = None

# 통계 추적
recognition_stats = {
    "total_tests": 0,
    "successful": 0,
    "failed": 0,
    "total_confidence": 0.0,
    "total_processing_time": 0.0,
}

VERSION = "2.0.0"  # Advanced scenarios support


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 초기화."""
    global product_db, decision_engine, top5_extractor
    global multi_hand_detector, return_detector, cross_zone_detector
    global baseline_manager, rapid_pickup_handler

    # 시작
    logger.info("Initializing Product Judgment Service v2.0...")
    product_db = ProductDatabase()
    decision_engine = ProductDecisionEngine(product_db)
    top5_extractor = Top5Extractor()

    # Advanced scenario components
    multi_hand_detector = MultiHandDetector()
    return_detector = ReturnDetector()
    cross_zone_detector = CrossZoneDetector()
    baseline_manager = BaselineManager()
    rapid_pickup_handler = RapidPickupHandler()

    logger.info(f"Service ready. {product_db.product_count} products loaded.")
    logger.info("Advanced scenarios enabled: multi-zone, return detection, rapid pickup")

    yield

    # 종료
    logger.info("Shutting down Product Judgment Service...")


# FastAPI 앱 생성
app = FastAPI(
    title="Product Judgment Service",
    description="AI 스마트 자판기 상품 판단 서비스 - Vision + Weight Fusion",
    version=VERSION,
    lifespan=lifespan,
)

# CORS 설정 (Node.js 연동용)
# 환경변수: CORS_ORIGINS (쉼표 구분, 예: "http://localhost:3000,http://localhost:8000")
# 기본값: 개발 환경에서는 모든 origin 허용, 프로덕션에서는 환경변수로 제한
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
_cors_origins = (
    [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
    if _cors_origins_env
    else ["*"]  # 개발 환경 기본값
)
_allow_credentials = os.getenv("CORS_CREDENTIALS", "true").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials if _cors_origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== API Endpoints ==========

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """헬스 체크."""
    return HealthResponse(
        status="ok",
        version=VERSION,
        product_count=product_db.product_count if product_db else 0,
    )


@app.get("/api/products", tags=["Products"])
async def get_products():
    """등록된 상품 목록 조회."""
    if not product_db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    products = product_db.get_all_products()
    return {
        "count": len(products),
        "products": [p.to_dict() for p in products],
    }


@app.get("/api/products/{product_id}", tags=["Products"])
async def get_product(product_id: int):
    """특정 상품 정보 조회."""
    if not product_db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    product = product_db.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    return product.to_dict()


@app.post("/api/test", response_model=JudgeResponse, tags=["Test"])
async def test_judge(request: TestRequest):
    """
    테스트용 상품 판단 (로드셀 연결 없이).

    YOLO 감지 결과와 무게 변화량을 직접 입력하여 테스트.
    Node.js 전체 결제 프로세스 점검용.

    Example:
        POST /api/test
        {
            "detections": [
                {"xyxy": [258.72, 47.65, 315.12, 113.97], "conf": 0.788, "cls": 0, "name": "hand"},
                {"xyxy": [257.67, 75.54, 284.33, 110.22], "conf": 0.492, "cls": 26, "name": "chickenmayo_rice"}
            ],
            "delta_weight": -365.0
        }
    """
    if not decision_engine or not top5_extractor:
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        # 1. YOLO Detection 파싱
        detections = [
            YOLODetection(
                xyxy=tuple(d.xyxy),
                conf=d.conf,
                cls=d.cls,
                name=d.name,
            )
            for d in request.detections
        ]

        logger.info(f"Test request: {len(detections)} detections, delta={request.delta_weight}g")

        # 2. Top-5 추출 (손 근접 필터 선택적)
        if request.use_hand_filter:
            candidates = top5_extractor.process_single_camera(detections)
        else:
            # 필터 없이 모든 상품
            candidates = [
                EnsembleResult(
                    class_id=d.cls,
                    class_name=d.name,
                    top_confidence=d.conf,
                    side_confidence=0.0,
                    combined_confidence=d.conf,
                    vote_count=1,
                )
                for d in detections if d.cls != 0
            ]
            candidates.sort(key=lambda c: c.combined_confidence, reverse=True)
            candidates = candidates[:5]

        # 3. 상품 판단
        result = decision_engine.judge(candidates, request.delta_weight)

        # 4. 응답 변환
        return _convert_to_response(result)

    except Exception as e:
        logger.error(f"Test judge error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simulate", response_model=JudgeResponse, tags=["Test"])
async def simulate_judge(request: SimulateRequest):
    """
    시뮬레이션 상품 판단 (product_id + count 직접 지정).

    상품 ID와 개수를 직접 지정하여 결과 생성.
    테스트/데모용.

    Example:
        POST /api/simulate
        {
            "product_id": 26,
            "count": 1,
            "confidence": 0.85
        }
    """
    if not decision_engine or not product_db:
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        product = product_db.get_product(request.product_id)
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {request.product_id} not found"
            )

        # 가상의 delta_weight 계산
        delta_weight = -(product.weight * request.count)

        # 가상의 EnsembleResult 생성
        candidates = [
            EnsembleResult(
                class_id=request.product_id,
                class_name=product.name,
                top_confidence=request.confidence,
                side_confidence=request.confidence,
                combined_confidence=request.confidence,
                vote_count=2,
            )
        ]

        # 판단
        result = decision_engine.judge(candidates, delta_weight)

        return _convert_to_response(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simulate error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/judge", response_model=JudgeResponse, tags=["Production"])
async def judge_product(request: JudgeRequest):
    """
    실제 상품 판단 (스냅샷 + 로드셀).

    프로덕션 환경에서 사용:
    1. snapshot_folder에서 이미지 로드
    2. YOLO 추론
    3. 손 근접 필터링 + Top-5 추출
    4. 무게 기반 검증
    5. 최종 결과 반환

    Example:
        POST /api/judge
        {
            "snapshot_folder": "/data/260116_1200/",
            "loadcell_weights": [500, 500, 0, 0, 0, 0, 0, 0, 0, 0],
            "baseline_weights": [865, 500, 0, 0, 0, 0, 0, 0, 0, 0],
            "zone_id": 0
        }
    """
    if not decision_engine:
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        # 무게 변화량 계산
        deltas = [
            curr - base
            for curr, base in zip(request.loadcell_weights, request.baseline_weights)
        ]

        if request.zone_id is not None:
            start_idx = request.zone_id * 2
            delta_weight = sum(deltas[start_idx:start_idx + 2])
        else:
            delta_weight = sum(deltas)

        logger.info(
            f"Judge request: folder={request.snapshot_folder}, "
            f"delta={delta_weight:.1f}g, zone={request.zone_id}"
        )

        # TODO: 실제 구현에서는 이미지 로드 + YOLO 추론 추가
        # 현재는 이미지 없이 빈 결과 반환 (테스트용)

        # 임시: 빈 후보군으로 판단
        candidates: List[EnsembleResult] = []
        result = decision_engine.judge(candidates, delta_weight)

        return _convert_to_response(result)

    except Exception as e:
        logger.error(f"Judge error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========== Advanced Scenario Endpoints ==========

@app.post("/api/judge/multi-zone", response_model=MultiZoneJudgeResponse, tags=["Advanced"])
async def judge_multi_zone(request: MultiZoneJudgeRequest):
    """
    다중 Zone 동시 판단 (시나리오 4, 6).

    다중 사용자 동시 취출 또는 Zone 간 상품 이동 처리.

    시나리오 4: 3명까지 동시에 다른 선반에서 상품 취출
    시나리오 6: 상품을 다른 위치로 이동 후 구매

    Example:
        POST /api/judge/multi-zone
        {
            "zone_deltas": [
                {"zone_id": 0, "delta": -365.0},
                {"zone_id": 2, "delta": -130.0}
            ],
            "detections": [...],
            "door_open_duration": 0.0
        }
    """
    if not decision_engine or not multi_hand_detector or not cross_zone_detector:
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        import time
        start_time = time.time()

        # 1. Cross-Zone 이동 체크
        cross_zone_movement = None
        if request.check_cross_zone:
            zone_deltas = [(zd.zone_id, zd.delta) for zd in request.zone_deltas]
            movement = cross_zone_detector.detect(zone_deltas)
            if movement.is_movement:
                cross_zone_movement = CrossZoneMovementModel(
                    detected=True,
                    source_zone=movement.source_zone,
                    target_zone=movement.target_zone,
                    weight=movement.weight,
                    movement_type=movement.movement_type,
                )
                # 이동만 있고 실제 취출 없으면 빈 결과 반환
                logger.info(f"Cross-zone movement detected, skipping payment")
                return MultiZoneJudgeResponse(
                    success=True,
                    zone_results=[],
                    total_price=0,
                    cross_zone_movement=cross_zone_movement,
                    person_count=0,
                    timestamp=time.time(),
                )

        # 2. YOLO Detection 파싱
        detections = [
            YOLODetection(
                xyxy=tuple(d.xyxy),
                conf=d.conf,
                cls=d.cls,
                name=d.name,
            )
            for d in request.detections
        ]

        # 3. Multi-hand 감지
        multi_hand_result = multi_hand_detector.filter(detections)
        person_count = multi_hand_result.person_count

        # 4. Zone별 판단
        zone_results = []
        total_price = 0

        for zd in request.zone_deltas:
            if abs(zd.delta) < 5.0:  # 최소 무게 변화
                continue

            # Baseline 드리프트 보정 (시나리오 7)
            corrected_delta = zd.delta
            if request.door_open_duration > 0 and baseline_manager:
                corrected_delta = baseline_manager.get_long_open_correction(
                    zone_id=zd.zone_id,
                    door_open_duration=request.door_open_duration,
                    current_weight=0.0,  # 상대값이므로 0 사용
                )
                corrected_delta = zd.delta  # 실제로는 현재 무게 필요

            # 해당 Zone의 상품 후보 추출
            zone_candidates = top5_extractor.process_single_camera(detections)

            # 판단 수행
            result = decision_engine.judge(zone_candidates, corrected_delta)

            zone_result = MultiZoneResult(
                zone_id=zd.zone_id,
                products=[
                    ProductOutput(
                        productId=p.product_id,
                        name=p.name,
                        count=p.count,
                        unitPrice=p.unit_price,
                        totalPrice=p.total_price,
                        confidence=round(p.confidence, 2),
                    )
                    for p in result.products
                ],
                total_price=result.total_price,
                confidence=round(result.confidence, 2),
                status=JudgmentStatusEnum(result.status.value),
            )
            zone_results.append(zone_result)
            total_price += result.total_price

        return MultiZoneJudgeResponse(
            success=bool(zone_results),
            zone_results=zone_results,
            total_price=total_price,
            cross_zone_movement=cross_zone_movement,
            person_count=max(person_count, len([z for z in zone_results if z.products])),
            timestamp=time.time(),
        )

    except Exception as e:
        logger.error(f"Multi-zone judge error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/judge/with-history", response_model=JudgeWithHistoryResponse, tags=["Advanced"])
async def judge_with_history(request: JudgeWithHistoryRequest):
    """
    이전 이벤트 기록 포함 판단 (시나리오 5, 8).

    반납 감지 및 연속 취출 처리.

    시나리오 5: 상품 선택 후 같은/다른 위치에 반납
    시나리오 8: 2~10개 상품 빠른 연속 취출

    Example:
        POST /api/judge/with-history
        {
            "current_request": {
                "detections": [],
                "delta_weight": 365.0,
                "zone_id": 0
            },
            "recent_events": [
                {"timestamp": 1737046790, "zone_id": 0, "delta": -365.0, "direction": "pickup"}
            ],
            "check_return": true
        }
    """
    if not decision_engine or not return_detector:
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        import time

        # 1. 이전 이벤트 기록 (반납 감지용)
        if request.check_return:
            for event in request.recent_events:
                if event.direction == "pickup" and event.delta < 0:
                    return_detector.record_pickup(
                        zone_id=event.zone_id,
                        weight=abs(event.delta),
                    )

        # 2. 반납 감지 (양수 무게 변화)
        return_detection = None
        if request.check_return and request.current_request.delta_weight > 0:
            zone_id = request.current_request.zone_id or 0
            return_result = return_detector.check_return(
                zone_id=zone_id,
                positive_delta=request.current_request.delta_weight,
            )

            if return_result.is_return:
                return_detection = ReturnDetectionResult(
                    is_return=True,
                    original_weight=return_result.pickup_event.weight if return_result.pickup_event else None,
                    return_weight=request.current_request.delta_weight,
                    match_score=return_result.match_score,
                    should_cancel_payment=return_result.should_cancel_payment,
                    return_type=return_result.return_type,
                )

                # 반납이면 빈 판단 결과 반환
                empty_response = JudgeResponse(
                    success=False,
                    products=[],
                    totalPrice=0,
                    status=JudgmentStatusEnum.NO_DETECTION,
                    confidence=0.0,
                    weightInfo=WeightInfo(
                        delta=request.current_request.delta_weight,
                        explained=0.0,
                        residual=request.current_request.delta_weight,
                    ),
                    productCount=0,
                    isRemoval=False,
                    timestamp=time.time(),
                )

                return JudgeWithHistoryResponse(
                    judgment_result=empty_response,
                    return_detection=return_detection,
                    is_rapid_pickup=False,
                    event_count=len(request.recent_events) + 1,
                )

        # 3. 일반 판단 수행
        detections = [
            YOLODetection(
                xyxy=tuple(d.xyxy),
                conf=d.conf,
                cls=d.cls,
                name=d.name,
            )
            for d in request.current_request.detections
        ]

        if request.current_request.use_hand_filter:
            candidates = top5_extractor.process_single_camera(detections)
        else:
            candidates = [
                EnsembleResult(
                    class_id=d.cls,
                    class_name=d.name,
                    top_confidence=d.conf,
                    side_confidence=0.0,
                    combined_confidence=d.conf,
                    vote_count=1,
                )
                for d in detections if d.cls != 0
            ]
            candidates.sort(key=lambda c: c.combined_confidence, reverse=True)
            candidates = candidates[:5]

        result = decision_engine.judge(candidates, request.current_request.delta_weight)
        judgment_response = _convert_to_response(result)

        # 연속 취출 여부 판단
        is_rapid = len(request.recent_events) >= 2

        return JudgeWithHistoryResponse(
            judgment_result=judgment_response,
            return_detection=return_detection,
            is_rapid_pickup=is_rapid,
            event_count=len(request.recent_events) + 1,
        )

    except Exception as e:
        logger.error(f"Judge with history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats/recognition-rate", response_model=RecognitionStats, tags=["Statistics"])
async def get_recognition_stats():
    """
    인식률 통계 조회 (시나리오 2).

    100회 테스트 기준 인식률 측정용.
    """
    total = recognition_stats["total_tests"]
    successful = recognition_stats["successful"]

    if total == 0:
        return RecognitionStats(
            total_tests=0,
            successful=0,
            failed=0,
            recognition_rate=0.0,
            avg_confidence=0.0,
            avg_processing_time_ms=0.0,
        )

    return RecognitionStats(
        total_tests=total,
        successful=successful,
        failed=total - successful,
        recognition_rate=(successful / total) * 100.0,
        avg_confidence=recognition_stats["total_confidence"] / total,
        avg_processing_time_ms=recognition_stats["total_processing_time"] / total,
    )


@app.post("/api/stats/reset", tags=["Statistics"])
async def reset_recognition_stats():
    """인식률 통계 초기화."""
    global recognition_stats
    recognition_stats = {
        "total_tests": 0,
        "successful": 0,
        "failed": 0,
        "total_confidence": 0.0,
        "total_processing_time": 0.0,
    }
    return {"status": "reset", "message": "Recognition stats cleared"}


# ========== Helper Functions ==========

def _convert_to_response(result) -> JudgeResponse:
    """JudgmentResult를 JudgeResponse로 변환."""
    products = [
        ProductOutput(
            productId=p.product_id,
            name=p.name,
            count=p.count,
            unitPrice=p.unit_price,
            totalPrice=p.total_price,
            confidence=round(p.confidence, 2),
        )
        for p in result.products
    ]

    # JudgmentStatus enum 변환
    status_map = {
        JudgmentStatus.COMPLETE: JudgmentStatusEnum.COMPLETE,
        JudgmentStatus.PARTIAL: JudgmentStatusEnum.PARTIAL,
        JudgmentStatus.UNCERTAIN: JudgmentStatusEnum.UNCERTAIN,
        JudgmentStatus.NO_DETECTION: JudgmentStatusEnum.NO_DETECTION,
    }

    return JudgeResponse(
        success=result.is_success,
        products=products,
        totalPrice=result.total_price,
        status=status_map[result.status],
        confidence=round(result.confidence, 2),
        weightInfo=WeightInfo(
            delta=round(result.weight_delta, 1),
            explained=round(result.weight_explained, 1),
            residual=round(result.weight_residual, 1),
        ),
        productCount=result.product_count,
        isRemoval=result.is_removal,
        timestamp=result.timestamp,
    )


# ========== CLI Entry Point ==========

def main():
    """CLI 진입점."""
    import uvicorn
    uvicorn.run(
        "product_judge.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
    )


if __name__ == "__main__":
    main()
