"""
Serial communication layer for IO Board.

This module provides async serial communication with the IO Board device,
including retry logic with exponential backoff, structured logging, and
comprehensive error handling.
"""

import asyncio
import os
import random
from typing import Optional

import serial
import serial_asyncio

from .config import SerialConfig
from .exceptions import ErrorCode, SerialCommunicationError
from .logging_config import PerformanceLogger, get_logger, log_payload

logger = get_logger(__name__)

# Mock mode flag
MOCK_MODE = os.getenv("IO_BOARD_MOCK_MODE", "false").lower() in ("true", "1", "yes")

# Global serial configuration and mutex
_serial_config: Optional[SerialConfig] = None
_serial_mutex = asyncio.Lock()


def configure_serial(config: SerialConfig) -> None:
    """
    Configure serial communication parameters.

    Args:
        config: Serial configuration object
    """
    global _serial_config
    _serial_config = config
    logger.info(
        f"Serial configured: port={config.port} baudrate={config.baudrate} "
        f"timeouts=({config.header_timeout}s/{config.body_timeout}s/{config.checksum_timeout}s) "
        f"retries={config.max_retries}"
    )


def get_serial_config() -> SerialConfig:
    """
    Get current serial configuration.

    Returns:
        Serial configuration object

    Raises:
        SerialCommunicationError: If serial not configured
    """
    if _serial_config is None:
        raise SerialCommunicationError(
            "Serial communication not configured",
            ErrorCode.SERIAL_CONNECTION_FAILED,
            {"reason": "configure_serial() must be called before use"}
        )
    return _serial_config


def _generate_mock_response(message: bytes) -> bytes:
    """
    Generate mock response for testing without hardware.

    Args:
        message: Request message to generate mock response for

    Returns:
        Mock binary response matching expected protocol format
    """
    from functools import reduce

    # Parse command from request (after STX byte)
    if len(message) < 6:
        return b""

    cmd = message[1:3].decode('ascii')
    subcmd = message[3:5].decode('ascii')
    cmd_subcmd = cmd + subcmd

    # Generate mock data based on command
    if cmd_subcmd == "RQIW":  # Loadcell weights (10 readings x 6 chars)
        loadcells = ""
        for _ in range(10):
            weight = random.randint(-100, 5000)
            loadcells += f"{weight:+06d}"
        data = loadcells.encode('ascii')
    elif cmd_subcmd == "RQID":  # IO status (door 6 chars + deadbolt 6 chars)
        data = b"CLOSEDCLOSED"
    elif cmd_subcmd == "RQMI":  # Manufacturing info (product_id 11 + sw_version 2)
        data = b"MOCKDEVICE112"
    elif cmd_subcmd == "RQER":  # Error list (4 errors x 4 chars)
        data = b"0000000000000000"
    elif cmd_subcmd == "MCDC":  # Door control - echo back door state byte
        door_byte = message[5] if len(message) > 5 else ord('C')
        data = bytes([door_byte])
    elif cmd_subcmd == "MCWP":  # Write product ID - echo back
        data = message[5:16] if len(message) >= 16 else b"MOCKDEVICE1"
    else:
        # Generic success response (no data) for MCPD, MCLZ, MCEZ, MCRT
        data = b""

    # Build response frame: STX + CMD + SUBCMD + DATA + ETX + CHECKSUM
    # Checksum is XOR of all bytes between STX and checksum (including ETX)
    response_body = cmd.encode('ascii') + subcmd.encode('ascii') + data + b"\x03"
    checksum = reduce(lambda x, y: x ^ y, response_body, 0)
    response = b"\x02" + response_body + bytes([checksum])

    return response


async def _fetch_with_timeout(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    message: bytes
) -> bytes:
    """
    Send message and receive response with appropriate timeouts.

    This internal function handles the low-level serial I/O with timeouts
    for each phase of the protocol frame.

    Args:
        reader: Async stream reader for serial port
        writer: Async stream writer for serial port
        message: Binary message to send

    Returns:
        Complete binary response message

    Raises:
        asyncio.TimeoutError: If any read operation times out
        asyncio.IncompleteReadError: If connection closes before response complete
    """
    config = get_serial_config()

    # Send request message
    log_payload(logger, "TX", message, "request")
    writer.write(message)
    await writer.drain()

    # Read response frame in three phases with appropriate timeouts
    response = b""

    # Phase 1: Read STX (Start of Text) byte
    response += await asyncio.wait_for(
        reader.readexactly(1),
        timeout=config.header_timeout
    )

    # Phase 2: Read until ETX (End of Text) byte
    response += await asyncio.wait_for(
        reader.readuntil(b"\x03"),
        timeout=config.body_timeout
    )

    # Phase 3: Read checksum byte
    response += await asyncio.wait_for(
        reader.readexactly(1),
        timeout=config.checksum_timeout
    )

    log_payload(logger, "RX", response, "response")
    return response


async def fetch(message: bytes) -> bytes:
    """
    Send message to IO Board and receive response with retry logic.

    This function implements thread-safe serial communication with:
    - Mutex-based exclusive access
    - Exponential backoff retry strategy
    - Comprehensive error handling and logging
    - Automatic connection management

    Args:
        message: Binary protocol message to send

    Returns:
        Binary protocol response from device

    Raises:
        SerialCommunicationError: If communication fails after all retries
    """
    # Mock mode - return simulated responses
    if MOCK_MODE:
        log_payload(logger, "TX (MOCK)", message, "request")
        await asyncio.sleep(0.01)  # Simulate small delay
        response = _generate_mock_response(message)
        log_payload(logger, "RX (MOCK)", response, "response")
        return response

    config = get_serial_config()

    async with _serial_mutex:
        with PerformanceLogger(logger, "serial_fetch", port=config.port):
            # Open serial connection
            try:
                logger.debug(f"Opening serial port: {config.port} @ {config.baudrate} baud")
                reader, writer = await serial_asyncio.open_serial_connection(
                    url=config.port,
                    baudrate=config.baudrate,
                )
            except serial.SerialException as e:
                error_msg = str(e).lower()

                # Categorize serial errors
                if "access is denied" in error_msg or "permission" in error_msg:
                    raise SerialCommunicationError(
                        f"Permission denied accessing serial port",
                        ErrorCode.SERIAL_PORT_PERMISSION_DENIED,
                        {"port": config.port}
                    ) from e
                elif "cannot find" in error_msg or "does not exist" in error_msg:
                    raise SerialCommunicationError(
                        f"Serial port not found",
                        ErrorCode.SERIAL_PORT_NOT_FOUND,
                        {"port": config.port}
                    ) from e
                elif "busy" in error_msg or "in use" in error_msg:
                    raise SerialCommunicationError(
                        f"Serial port busy or already in use",
                        ErrorCode.SERIAL_PORT_BUSY,
                        {"port": config.port}
                    ) from e
                else:
                    raise SerialCommunicationError(
                        f"Failed to open serial port",
                        ErrorCode.SERIAL_CONNECTION_FAILED,
                        {"port": config.port, "error": str(e)}
                    ) from e

            try:
                # Retry loop with exponential backoff
                retry_delay = config.initial_retry_delay
                last_exception: Optional[Exception] = None

                for attempt in range(1, config.max_retries + 1):
                    try:
                        logger.debug(f"Attempt {attempt}/{config.max_retries}")
                        response = await _fetch_with_timeout(reader, writer, message)
                        logger.debug(f"Fetch successful on attempt {attempt}")
                        return response

                    except asyncio.TimeoutError as e:
                        last_exception = e
                        logger.warning(
                            f"Timeout on attempt {attempt}/{config.max_retries} "
                            f"(will retry in {retry_delay:.3f}s)"
                        )

                        if attempt < config.max_retries:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= config.retry_backoff_multiplier

                    except asyncio.IncompleteReadError as e:
                        last_exception = e
                        logger.warning(
                            f"Incomplete read on attempt {attempt}/{config.max_retries}: "
                            f"expected={e.expected} received={len(e.partial)} "
                            f"(will retry in {retry_delay:.3f}s)"
                        )

                        if attempt < config.max_retries:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= config.retry_backoff_multiplier

                # All retries exhausted
                if isinstance(last_exception, asyncio.TimeoutError):
                    raise SerialCommunicationError(
                        f"Serial read timeout after {config.max_retries} attempts",
                        ErrorCode.SERIAL_TIMEOUT,
                        {
                            "port": config.port,
                            "attempts": config.max_retries,
                            "message_hex": message.hex()
                        }
                    ) from last_exception
                else:
                    raise SerialCommunicationError(
                        f"Incomplete serial read after {config.max_retries} attempts",
                        ErrorCode.SERIAL_INCOMPLETE_READ,
                        {
                            "port": config.port,
                            "attempts": config.max_retries,
                            "message_hex": message.hex()
                        }
                    ) from last_exception

            finally:
                # Always close the connection
                logger.debug("Closing serial port")
                writer.close()
                await writer.wait_closed()
