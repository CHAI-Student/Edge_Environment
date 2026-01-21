"""
Model Service - FastAPI Entry Point.

AI 상품 판단 서비스.

실행 방법:
    # 일반 모드 (FastAPI 서버)
    uvicorn main:app --host 0.0.0.0 --port 8002 --reload

    # 테스트 모드 (콘솔 대시보드)
    python -m main --test

기능:
    - io_board SSE 구독 (loadcell.change 이벤트)
    - camera_driver 연동 (Top + Side 프레임 캡처)
    - YOLO 추론 (Hand-Proximity ROI 필터링)
    - 무게 기반 개수 검증
    - Node.js 결과 전송
"""

import argparse
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

from .config import config
from .database.product_db import ProductDatabase
from .engine import ProductDecisionEngine
from .api.routes import router, init_routes
from .api.node_client import NodeJSClient
from .sse_client import IOBoardSubscriber
from .sse_client.zone_detector import ZoneDetector

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# 전역 인스턴스
product_db: ProductDatabase = None
decision_engine: ProductDecisionEngine = None
node_client: NodeJSClient = None
sse_subscriber: IOBoardSubscriber = None
zone_detector: ZoneDetector = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 애플리케이션 수명 주기 관리."""
    global product_db, decision_engine, node_client, sse_subscriber, zone_detector

    logger.info("Model service starting...")

    # 컴포넌트 초기화
    product_db = ProductDatabase()
    decision_engine = ProductDecisionEngine(product_db=product_db)
    node_client = NodeJSClient(base_url=config.nodejs_url)
    zone_detector = ZoneDetector()

    # API 라우터 초기화
    init_routes(product_db, decision_engine)

    # SSE 구독자 초기화 및 시작
    async def on_loadcell_change(event):
        """로드셀 변화 이벤트 핸들러."""
        from .sse_client import LoadcellChangeEvent

        zone_info = zone_detector.get_primary_zone(
            changed_indices=event.changed_indices,
            old_values=event.old_values,
            new_values=event.new_values,
        )

        if zone_info:
            logger.info(
                f"Zone {zone_info.zone_id} change: delta={zone_info.delta_weight:.1f}g"
            )
            # 실제 판단 로직은 별도 태스크로 처리 (이벤트 루프 블로킹 방지)
            # asyncio.create_task(process_zone_event(zone_info))

    sse_subscriber = IOBoardSubscriber(
        base_url=config.io_board_url,
        on_change=on_loadcell_change,
    )

    # SSE 구독 시작 (백그라운드)
    asyncio.create_task(sse_subscriber.start())

    # Node.js 클라이언트 시작
    await node_client.start()

    logger.info(f"Model service ready on port {config.port}")

    yield

    # 종료 처리
    logger.info("Model service shutting down...")

    if sse_subscriber:
        await sse_subscriber.stop()

    if node_client:
        await node_client.stop()

    logger.info("Model service stopped")


# FastAPI 앱 생성
app = FastAPI(
    title="Model Service",
    description="AI 상품 판단 서비스 - Vision + Weight Fusion",
    version="1.0.0",
    lifespan=lifespan,
)

# 라우터 등록
app.include_router(router)


@app.get("/")
async def root():
    """루트 엔드포인트."""
    return {
        "service": "model",
        "version": "1.0.0",
        "description": "AI 상품 판단 서비스",
    }


def run_server():
    """FastAPI 서버 실행."""
    uvicorn.run(
        "Edge_Environment.services.model.main:app",
        host=config.host,
        port=config.port,
        reload=True,
        log_level="info",
    )


async def run_test_mode():
    """테스트 모드 실행."""
    from .monitor import TestModeHandler

    handler = TestModeHandler()

    try:
        await handler.run()
    except KeyboardInterrupt:
        logger.info("Test mode interrupted")
    finally:
        await handler.stop()


def main():
    """메인 진입점."""
    parser = argparse.ArgumentParser(description="Model Service")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode with console dashboard",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=config.host,
        help="Server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.port,
        help="Server port (default: 8002)",
    )
    parser.add_argument(
        "--io-board-url",
        type=str,
        default=config.io_board_url,
        help="io_board service URL",
    )
    parser.add_argument(
        "--camera-url",
        type=str,
        default=config.camera_driver_url,
        help="camera_driver service URL",
    )
    parser.add_argument(
        "--node-url",
        type=str,
        default=config.nodejs_url,
        help="Node.js orchestrator URL",
    )

    args = parser.parse_args()

    # 설정 업데이트
    config.host = args.host
    config.port = args.port
    config.io_board_url = args.io_board_url
    config.camera_driver_url = args.camera_url
    config.nodejs_url = args.node_url

    if args.test:
        # 테스트 모드
        logger.info("Starting test mode...")
        asyncio.run(run_test_mode())
    else:
        # 서버 모드
        logger.info(f"Starting server on {config.host}:{config.port}...")
        run_server()


if __name__ == "__main__":
    main()
