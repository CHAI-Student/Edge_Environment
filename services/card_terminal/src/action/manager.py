"""
Action manager for processing device-initiated events.

This module handles incoming device requests (token initialization, Samsung Pay,
RFID reads) and publishes events to the SSE stream for real-time client notifications.

Supports graceful shutdown via shutdown_event to cleanly terminate event processing.
"""

import asyncio
import logging

from api.schemas import RFIDStream, TokenGeneratedStream
from exceptions import DeviceError
from payment.const import ServiceCode, StatusCode
from payment.manager import Communication
from payment.command import retrieve_request, send_tx_token_generate

logger = logging.getLogger(__name__)


class Action:
    """
    Action manager for device-initiated events.

    Processes incoming device requests and publishes events to SSE stream.
    Supports graceful shutdown for clean application termination.
    """

    def __init__(
        self,
        comm: Communication,
        sse_queue: asyncio.Queue,
        shutdown_event: asyncio.Event,
    ):
        """
        Initialize action manager.

        Args:
            comm: Communication instance for device interaction
            sse_queue: Queue for publishing SSE events
            shutdown_event: Event to signal shutdown request
        """
        self.comm = comm
        self.sse_queue = sse_queue
        self.shutdown_event = shutdown_event
        self._running = False

    async def run(self):
        """
        Run the action manager event loop.

        Continuously processes device requests until shutdown is signaled.
        Handles token generation, Samsung Pay initialization, and RFID reads.
        """
        self._running = True
        logger.info("Action manager started")

        try:
            while not self.shutdown_event.is_set():
                # Wait for device request or shutdown signal
                request_task = asyncio.create_task(retrieve_request(self.comm))
                shutdown_task = asyncio.create_task(self.shutdown_event.wait())

                done, pending = await asyncio.wait(
                    [request_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if shutdown was signaled
                if self.shutdown_event.is_set():
                    logger.info("Shutdown signal received in action manager")
                    break

                # Process the device request
                try:
                    message, payload = await request_task
                    await self._handle_device_request(message, payload)
                except Exception as e:
                    logger.error(f"Error processing device request: {e}", exc_info=True)
                    continue

        finally:
            self._running = False
            logger.info("Action manager stopped")

    async def _handle_device_request(self, message, payload):
        """
        Handle a single device request.

        Args:
            message: Protocol message from device
            payload: Parsed payload data
        """
        if message.service_code == ServiceCode.TX_TOKEN_INIT.value:
            await self._handle_token_init()

        elif message.service_code == ServiceCode.TX_SPAY_INIT.value:
            await self._handle_samsung_pay_init()

        elif message.service_code == ServiceCode.TX_RFID_INIT.value:
            await self._handle_rfid_init(payload)

        else:
            logger.warning(f"Unhandled service code: {message.service_code}")

    async def _handle_token_init(self):
        """Handle token generation initialization request."""
        logger.debug("Processing TX_TOKEN_INIT request")

        try:
            tx_token_data = await send_tx_token_generate(self.comm)

            # Check status and raise error if failed
            if tx_token_data["status"] != StatusCode.Y:
                logger.warning(
                    f"Token generation failed with status: {tx_token_data['status']}, "
                    f"response_code: {tx_token_data['response_code'].name}"
                )
                raise DeviceError(
                    "Token generation failed",
                    response_code=tx_token_data["response_code"].name,
                )

            # Publish success event
            await self.sse_queue.put({
                "event": "tx_token_generate",
                "data": TokenGeneratedStream(
                    status='Y',
                    vankey_hash=tx_token_data["vankey_hash"],
                    card_info=tx_token_data["card_info"],
                    response_code=tx_token_data["response_code"].value,
                    message=tx_token_data["message"],
                ).model_dump(),
            })

            logger.info("Token generation event published")

        except Exception as e:
            logger.error(f"Token generation failed: {e}")
            # Publish error event
            await self.sse_queue.put({
                "event": "tx_token_generate_error",
                "data": {"error": str(e)},
            })

    async def _handle_samsung_pay_init(self):
        """Handle Samsung Pay initialization request."""
        logger.debug("Processing TX_SPAY_INIT request")

        await self.sse_queue.put({
            "event": "samsung_pay_init",
            "data": {},
        })

        logger.info("Samsung Pay init event published")

    async def _handle_rfid_init(self, payload):
        """
        Handle RFID card read request.

        Args:
            payload: RFID payload with card data
        """
        logger.debug("Processing TX_RFID_INIT request")

        await self.sse_queue.put({
            "event": "rfid_init",
            "data": RFIDStream(data=payload.data).model_dump(),
        })

        logger.info(f"RFID event published: {payload.data[:10]}...")

    async def shutdown(self):
        """
        Gracefully shutdown the action manager.

        Sets the shutdown event and waits for event loop to terminate.
        """
        logger.info("Shutting down action manager")
        self.shutdown_event.set()

        # Wait for run loop to finish (with timeout)
        timeout = 5.0
        start_time = asyncio.get_event_loop().time()
        while self._running and (asyncio.get_event_loop().time() - start_time) < timeout:
            await asyncio.sleep(0.1)

        if self._running:
            logger.warning("Action manager did not stop gracefully within timeout")
        else:
            logger.info("Action manager shutdown complete")
