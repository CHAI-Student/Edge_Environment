"""
IO Board Service - FastAPI Entry Point.

로드셀(10ch) + 데드볼트 제어 서비스
포트: 8000

실행 방법:
    python main.py

기능:
    - 로드셀 무게 읽기 (10채널)
    - 데드볼트 열기/닫기 제어
    - SSE 스트림 (loadcells, doors)
    - 녹화 서비스
"""

import asyncio
import sys

from api.manager import serve_api
from core.config import Settings
from core.logging_config import get_logger, setup_logging


def run():
    """Run the IO Board service (entry point for PM2)."""
    # Load settings
    settings = Settings()

    # Setup logging
    setup_logging(settings.api.log_level.upper())
    logger = get_logger(__name__)

    # Shared shutdown signal for cooperative streaming stop
    stop_event = asyncio.Event()

    logger.info(f"Starting IO Board Service on {settings.api.host}:{settings.api.port}")

    try:
        asyncio.run(serve_api(settings, stop_event))
    except KeyboardInterrupt:
        logger.info("IO Board service stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"IO Board service failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
