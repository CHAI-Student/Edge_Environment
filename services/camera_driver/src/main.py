"""
Camera Driver Service - FastAPI Entry Point.

FastAPI 기반 6대 카메라 드라이버 서비스
포트: 8003

실행 방법:
    python main.py

Event-Driven Architecture:
    IO Board SSE -> Camera Driver (자체 버퍼링 & 저장)
                      | (media_paths 전송)
                  Node.js (10초 타이머 + 누적 로직)
"""

import asyncio
import sys

from api.manager import serve_api
from core.config import settings
from core.logging_config import get_logger, setup_logging


def run():
    """Run the Camera Driver service (entry point for PM2)."""
    # Setup logging
    setup_logging("INFO")
    logger = get_logger(__name__)

    logger.info(f"Starting Camera Driver Service on {settings.api_host}:{settings.api_port}")

    try:
        asyncio.run(serve_api())
    except KeyboardInterrupt:
        logger.info("Camera Driver stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Camera Driver failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
