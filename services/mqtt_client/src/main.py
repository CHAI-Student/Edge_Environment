"""
MQTT Client Service - FastAPI Entry Point.

FastAPI 래퍼를 통한 MQTT 클라이언트 서비스
포트: 8006

실행 방법:
    python main.py

NOTE:
    - Node.js 서버가 IF01, IF02, IF03를 담당합니다.
    - Python mqtt_client는 IF04 및 향후 추가되는 인터페이스만 담당합니다.
"""

import asyncio
import sys

from api.manager import serve_api
from core.config import settings
from core.logging_config import get_logger, setup_logging

# =============================================================================
# Protocol Imports (Handler Registration)
# =============================================================================
# NOTE: 프로토콜 모듈 import 시 핸들러가 자동으로 등록됩니다.
#
# Node.js 담당 (server/routes/Mqtt/):
#   - IF01 (Reboot): RebootMqtt.js
#   - IF02 (Health Check): HealthMqtt.js
#   - IF03 (Manual Door): ManualDoor.js
#
# Python 담당:
#   - IF04 (Collect Door): 수거함 도어 제어
#   - IF05+ (향후 추가)
# =============================================================================
from protocol import IF04  # noqa: F401 - Handler registration


def run():
    """Run the MQTT Client service (entry point for PM2)."""
    # Setup logging
    setup_logging(settings.log_level.upper())
    logger = get_logger(__name__)

    logger.info(f"Starting MQTT Client Service on {settings.api_host}:{settings.api_port}")

    try:
        asyncio.run(serve_api())
    except KeyboardInterrupt:
        logger.info("MQTT Client stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"MQTT Client failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
