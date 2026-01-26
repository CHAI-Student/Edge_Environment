"""
Model Service - FastAPI Entry Point.

AI 상품 판단 서비스 (경량화 버전).

실행 방법:
    # 일반 모드 (FastAPI 서버)
    uvicorn main:app --host 0.0.0.0 --port 8002 --reload

    # 테스트 모드 (콘솔 대시보드)
    python -m main --test

기능:
    - Node.js로부터 무게 데이터 + 이미지 경로 수신
    - YOLO 추론 (Hand-Proximity ROI 필터링)
    - 무게 기반 개수 검증
    - 판단 결과 반환 (stateless)

Note:
    SSE 구독과 카메라 직접 호출이 제거되었습니다.
    모든 데이터는 Node.js 오케스트레이터가 수집하여 전달합니다.
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 애플리케이션 수명 주기 관리."""
    global product_db, decision_engine, node_client

    logger.info("Model service starting (lightweight mode)...")

    # 컴포넌트 초기화
    product_db = ProductDatabase()
    decision_engine = ProductDecisionEngine(product_db=product_db)
    node_client = NodeJSClient(base_url=config.nodejs_url)

    # API 라우터 초기화
    init_routes(product_db, decision_engine)

    # Node.js 클라이언트 시작
    await node_client.start()

    logger.info(f"Model service ready on port {config.port} (judgment-only)")

    yield

    # 종료 처리
    logger.info("Model service shutting down...")

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
    parser = argparse.ArgumentParser(description="Model Service (Lightweight)")
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
        "--node-url",
        type=str,
        default=config.nodejs_url,
        help="Node.js orchestrator URL",
    )

    args = parser.parse_args()

    # 설정 업데이트
    config.host = args.host
    config.port = args.port
    config.nodejs_url = args.node_url

    if args.test:
        # 테스트 모드
        logger.info("Starting test mode...")
        asyncio.run(run_test_mode())
    else:
        # 서버 모드
        logger.info(f"Starting lightweight server on {config.host}:{config.port}...")
        run_server()


if __name__ == "__main__":
    main()
