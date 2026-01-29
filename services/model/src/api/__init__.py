"""
API module for Model service.

REST API 엔드포인트 및 Node.js 통신.

엔드포인트:
- GET /api/health: 헬스 체크
- POST /api/judge: 상품 판단
- GET /api/products: 상품 목록
- POST /api/judge/multi-zone: 다중 Zone 동시 판단
- POST /api/judge/with-history: 히스토리 기반 판단
- GET /api/stats/recognition-rate: 인식률 통계
"""

from .routes import router, init_routes
from .node_client import NodeJSClient
from .models import (
    # Multi-Zone
    MultiZoneJudgeRequest,
    MultiZoneJudgeResponse,
    ZoneJudgmentResult,
    CrossZoneMovementResult,
    # History
    HistoryJudgeRequest,
    HistoryJudgeResponse,
    ReturnDetectionResult,
    RapidPickupResult,
    # Stats
    RecognitionRateResponse,
    ZoneStatistics,
)

__all__ = [
    "router",
    "init_routes",
    "NodeJSClient",
    # Multi-Zone models
    "MultiZoneJudgeRequest",
    "MultiZoneJudgeResponse",
    "ZoneJudgmentResult",
    "CrossZoneMovementResult",
    # History models
    "HistoryJudgeRequest",
    "HistoryJudgeResponse",
    "ReturnDetectionResult",
    "RapidPickupResult",
    # Stats models
    "RecognitionRateResponse",
    "ZoneStatistics",
]
