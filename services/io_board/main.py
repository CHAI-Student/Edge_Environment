"""
IO Board Service entry point.

This module provides the main entry point for running the IO Board service
as a standalone FastAPI application on port 8001.

Usage:
    python -m main
    or
    uvicorn main:app --host 0.0.0.0 --port 8001 --reload
"""

import asyncio
import sys

from .api import app, serve_api
from .config import api_config, serial_config
from .serial_io import configure_serial
from .logging_config import get_logger

logger = get_logger(__name__)


async def main() -> None:
    """
    Main entry point for IO Board service.

    Configures serial communication and starts the FastAPI server.
    """
    logger.info("Starting IO Board Service v2.0.0")

    # Configure serial communication
    configure_serial(serial_config)

    # Start API server
    await serve_api(api_config)


def run() -> None:
    """Run the IO Board service."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("IO Board service stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"IO Board service failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
