"""
Product Judgment Service.

AI 스마트 자판기 상품 판단 모듈.

Vision (YOLO) + Weight (LoadCell) Fusion으로 상품 판단.

주요 모듈:
- engine: 판단 엔진 및 데이터 모델
- vision: YOLO 래퍼, 손 근접 필터, Top-5 추출
- weight: 무게 기반 개수 계산
- database: 상품 정보 DB
- interfaces: Node.js 연동 API

사용 예시:
    from product_judge import ProductDecisionEngine, ProductDatabase, Top5Extractor

    # 초기화
    db = ProductDatabase()
    engine = ProductDecisionEngine(db)
    extractor = Top5Extractor()

    # 판단 (테스트)
    candidates = extractor.process_single_camera(yolo_detections)
    result = engine.judge(candidates, delta_weight=-365.0)

    # Node.js 응답 형식
    response = result.to_node_response()
"""

__version__ = "1.0.0"
__author__ = "CRK Team"

# 핵심 클래스 export
from .engine.models import (
    Detection,
    EnsembleResult,
    CountEstimate,
    ProductJudgment,
    JudgmentResult,
    JudgmentStatus,
    ProductInfo,
    JudgmentRequest,
)
from .engine.decision_engine import ProductDecisionEngine
from .database.product_db import ProductDatabase
from .weight.count_calculator import WeightBasedCountCalculator
from .vision.yolo_wrapper import YOLOWrapper, YOLODetection
from .vision.hand_filter import HandProximityFilter
from .vision.top5_extractor import Top5Extractor

__all__ = [
    # Version
    "__version__",
    # Engine
    "ProductDecisionEngine",
    "Detection",
    "EnsembleResult",
    "CountEstimate",
    "ProductJudgment",
    "JudgmentResult",
    "JudgmentStatus",
    "ProductInfo",
    "JudgmentRequest",
    # Database
    "ProductDatabase",
    # Weight
    "WeightBasedCountCalculator",
    # Vision
    "YOLOWrapper",
    "YOLODetection",
    "HandProximityFilter",
    "Top5Extractor",
]
