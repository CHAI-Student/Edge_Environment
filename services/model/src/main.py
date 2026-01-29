"""
Model Service - FastAPI Entry Point.

AI 상품 판단 서비스 (경량화 버전).

실행 방법:
    # 일반 모드 (FastAPI 서버)
    python main.py

    # 테스트 모드 (콘솔 대시보드)
    python main.py --test

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
import sys

from api.manager import serve_api
from core.config import Settings
from core.logging_config import get_logger, setup_logging


async def run_test_mode(logger):
    """테스트 모드 실행."""
    from monitor import TestModeHandler

    handler = TestModeHandler()

    try:
        await handler.run()
    except KeyboardInterrupt:
        logger.info("Test mode interrupted")
    finally:
        await handler.stop()


def main():
    """메인 진입점."""
    # Load settings
    settings = Settings()

    # Setup logging
    setup_logging(settings.log_level.upper())
    logger = get_logger(__name__)

    parser = argparse.ArgumentParser(description="Model Service (Lightweight)")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode with console dashboard",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=settings.host,
        help="Server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.port,
        help="Server port (default: 8002)",
    )
    parser.add_argument(
        "--node-url",
        type=str,
        default=settings.nodejs_url,
        help="Node.js orchestrator URL",
    )

    args = parser.parse_args()

    # Update settings from CLI args (for backward compatibility)
    if args.host != settings.host:
        settings.api.host = args.host
    if args.port != settings.port:
        settings.api.port = args.port
    if args.node_url != settings.nodejs_url:
        settings.nodejs_url = args.node_url

    if args.test:
        # 테스트 모드
        logger.info("Starting test mode...")
        asyncio.run(run_test_mode(logger))
    else:
        # 서버 모드
        logger.info(f"Starting Model Service on {settings.host}:{settings.port}")
        asyncio.run(serve_api(settings))


def run():
    """Run the Model service (entry point for PM2)."""
    try:
        main()
    except KeyboardInterrupt:
        print("Model service stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Model service failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()
