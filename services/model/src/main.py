"""
Model Service - FastAPI Entry Point.

AI 상품 판단 서비스 (v3.0 - Frame Buffer API).

실행 방법:
    python main.py

기능:
    - POST /api/frame: 이미지 프레임 수신 (메모리 버퍼 저장)
    - POST /api/judge: 상품 판단 (버퍼에서 이미지 조회)
    - GET /api/products: 상품 목록

Note:
    카메라에서 직접 이미지를 수신하여 버퍼에 저장합니다.
    Node.js는 무게 데이터와 세션 ID만 전달합니다.
"""

import argparse
import asyncio
import sys

from api.manager import serve_api
from core.config import Settings
from core.logging_config import get_logger, setup_logging


def main():
    """메인 진입점."""
    # Load settings
    settings = Settings()

    # Setup logging
    setup_logging(settings.log_level.upper())
    logger = get_logger(__name__)

    parser = argparse.ArgumentParser(description="Model Service (v3.0 Frame Buffer)")
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

    args = parser.parse_args()

    # Update settings from CLI args
    if args.host != settings.host:
        settings.api.host = args.host
    if args.port != settings.port:
        settings.api.port = args.port

    # 서버 시작
    logger.info(f"Starting Model Service v3.0 on {settings.host}:{settings.port}")
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
