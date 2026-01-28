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


def sync_yolo_classes_to_product_db(product_db: ProductDatabase) -> int:
    """
    YOLO 모델의 클래스 이름을 ProductDatabase에 동기화.

    YOLO 모델에 정의된 클래스 중 ProductDatabase에 없는 것을 자동으로 등록합니다.
    이를 통해 Vision 전용 모드에서도 상품을 판단할 수 있습니다.

    Args:
        product_db: ProductDatabase 인스턴스

    Returns:
        동기화된 클래스 수
    """
    try:
        from .vision import YOLOWrapper

        yolo = YOLOWrapper(model_path=config.yolo_model_path)
        if not yolo.load():
            logger.warning("Failed to load YOLO model for class sync")
            return 0

        class_names = yolo.class_names
        if not class_names:
            logger.warning("YOLO model has no class names")
            return 0

        synced_count = 0
        for class_id, class_name in class_names.items():
            # hand (class_id=0)는 이미 있음, 스킵
            if class_id == 0:
                continue

            # 이미 등록된 상품인지 확인
            existing = product_db.get_product(class_id)
            if existing is not None:
                continue

            # 클래스 이름에서 카테고리와 가격 추측
            category = product_db._guess_category(class_name)

            # 새 상품 등록 (무게는 0, 가격은 1000원 기본값)
            # 실제 무게/가격은 IF11 동기화 또는 관리자 설정으로 업데이트
            try:
                product_db.add_product(
                    name=class_name,
                    category=category,
                    weight=0.0,  # 무게 미정 (IF11 동기화로 업데이트)
                    price=1000,  # 기본 가격 (IF11 동기화로 업데이트)
                    stock=0,
                    product_id=class_id,  # YOLO class_id와 동일하게 설정
                )
                synced_count += 1
                logger.debug(f"Synced YOLO class: id={class_id}, name={class_name}")
            except ValueError as e:
                logger.warning(f"Failed to sync class {class_id}: {e}")

        logger.info(f"Synced {synced_count} YOLO classes to ProductDatabase")
        return synced_count

    except ImportError as e:
        logger.warning(f"YOLO not available for class sync: {e}")
        return 0
    except Exception as e:
        logger.error(f"YOLO class sync failed: {e}")
        return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 애플리케이션 수명 주기 관리."""
    global product_db, decision_engine, node_client

    logger.info("Model service starting (lightweight mode)...")

    # 컴포넌트 초기화
    product_db = ProductDatabase()

    # YOLO 모델 클래스 동기화 (Vision 전용 모드 지원)
    sync_yolo_classes_to_product_db(product_db)

    decision_engine = ProductDecisionEngine(product_db=product_db)
    node_client = NodeJSClient(base_url=config.nodejs_url)

    # API 라우터 초기화
    init_routes(product_db, decision_engine)

    # Node.js 클라이언트 시작
    await node_client.start()

    logger.info(f"Model service ready on port {config.port} (judgment-only)")
    logger.info(f"ProductDatabase: {product_db.product_count} products registered")

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
