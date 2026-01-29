"""
FastAPI application for payment gateway.

This module provides the REST API for the payment gateway with:
- Token payment approval/cancellation
- Samsung Pay approval/cancellation
- Device health checks
- Real-time SSE event stream
- RFC 7807 compliant error handling
- Graceful shutdown support
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError as PydanticValidationError
from uvicorn.config import Config
from uvicorn.server import Server

from api.schemas import (
    PaymentTokenApproveRequest,
    PaymentTokenApproveResponse,
    PaymentTokenCancelRequest,
    PaymentTokenCancelResponse,
    ProblemDetail,
    SamsungPayApproveRequest,
    SamsungPayApproveResponse,
    SamsungPayCancelRequest,
    SamsungPayCancelResponse,
)
from exceptions import (
    PaymentGatewayError,
    ValidationError,
    CommunicationError,
    ProtocolError,
    TimeoutError as PaymentTimeoutError,
)
from payment.const import AuthorizationType, StatusCode
from payment.manager import Communication
from payment.command import (
    send_device_check,
    send_tx_spay_approve,
    send_tx_spay_cancel,
    send_tx_token_approve,
    send_tx_token_cancel,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Application State
# ============================================================================


@dataclass
class ApplicationState:
    """
    Application state container.

    Eliminates global mutable state by encapsulating all shared resources
    in a single container passed via FastAPI's app.state.
    """
    comm: Communication
    sse_queue: asyncio.Queue
    shutdown_event: asyncio.Event


def get_app_state(request: Request) -> ApplicationState:
    """
    FastAPI dependency to retrieve application state.

    Args:
        request: FastAPI request object

    Returns:
        Application state with communication, SSE queue, and shutdown event

    Raises:
        RuntimeError: If application state not initialized
    """
    if not hasattr(request.app.state, 'app_state'):
        raise RuntimeError("Application state not initialized")
    return request.app.state.app_state


# ============================================================================
# RFC 7807 Exception Handlers
# ============================================================================


async def payment_gateway_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Handle PaymentGatewayError exceptions with RFC 7807 Problem Details.

    Args:
        request: FastAPI request object
        exc: Payment gateway exception

    Returns:
        RFC 7807 compliant JSON response
    """
    if not isinstance(exc, PaymentGatewayError):
        return await generic_exception_handler(request, exc)

    problem_detail = exc.to_problem_detail()
    problem_detail["instance"] = str(request.url)

    logger.error(
        f"Payment gateway error: {exc.type_urn} - {exc.detail}",
        extra={"problem_detail": problem_detail}
    )

    return JSONResponse(
        status_code=exc.status,
        content=problem_detail,
        headers={"Content-Type": "application/problem+json"}
    )


async def validation_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Handle request validation errors with RFC 7807 Problem Details.

    Args:
        request: FastAPI request object
        exc: Validation error from Pydantic

    Returns:
        RFC 7807 compliant JSON response
    """
    if not isinstance(exc, RequestValidationError):
        return await generic_exception_handler(request, exc)

    validation_err = ValidationError(
        "Request validation failed",
        validation_errors=exc.errors(),
    )

    problem_detail = validation_err.to_problem_detail()
    problem_detail["instance"] = str(request.url)

    logger.warning(
        f"Validation error: {exc.errors()}",
        extra={"problem_detail": problem_detail}
    )

    return JSONResponse(
        status_code=validation_err.status,
        content=problem_detail,
        headers={"Content-Type": "application/problem+json"}
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Handle unexpected exceptions with RFC 7807 Problem Details.

    Args:
        request: FastAPI request object
        exc: Unexpected exception

    Returns:
        RFC 7807 compliant JSON response
    """
    logger.exception(f"Unexpected error: {exc}")

    problem_detail = {
        "type": "urn:payment-gateway:error:internal",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "An unexpected error occurred",
        "instance": str(request.url),
        "timestamp": datetime.now().isoformat(),
    }

    return JSONResponse(
        status_code=500,
        content=problem_detail,
        headers={"Content-Type": "application/problem+json"}
    )


# ============================================================================
# FastAPI Application
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup/shutdown."""
    # Startup
    logger.info("Starting FastAPI application")

    yield

    # Shutdown
    logger.info("Shutting down FastAPI application")


app = FastAPI(
    title="Payment Gateway API",
    description="Enterprise payment gateway for CAT device integration",
    version="2.0.0",
    lifespan=lifespan,
)

# Register RFC 7807 exception handlers
app.add_exception_handler(PaymentGatewayError, payment_gateway_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# ============================================================================
# Status & Health Endpoints
# ============================================================================


@app.get(
    "/status",
    response_model=dict,
    tags=["Status"],
    summary="Device health check",
    description="Check CAT device connectivity and readiness",
    responses={
        200: {
            "description": "Device is connected and ready",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Device connected",
                            "value": {
                                "status": "ok",
                                "response_code": 0x00,
                                "message": "SUCCESS"
                            }
                        },
                        "device_error": {
                            "summary": "Device not responding",
                            "value": {
                                "status": "error",
                                "response_code": 0xC1,
                                "message": "NETWORK_ERROR"
                            }
                        }
                    }
                }
            }
        }
    }
)
async def get_status(request: Request) -> dict:
    """
    Get device status check.

    Returns device status and response code indicating device health.
    """
    app_state = get_app_state(request)

    result = await send_device_check(app_state.comm)
    return {
        "status": "ok",
        "response_code": result["response_code"].value,
        "message": result["response_code"].name,
    }


# ============================================================================
# Token Payment Endpoints
# ============================================================================


@app.post(
    "/payment/token/approve",
    response_model=PaymentTokenApproveResponse,
    status_code=status.HTTP_200_OK,
    tags=["Token Payment"],
    summary="Approve token payment",
    description="Initiate a token-based payment transaction with the CAT device",
    responses={
        200: {
            "description": "Payment approved or declined",
            "content": {
                "application/json": {
                    "examples": {
                        "approved": {
                            "summary": "Payment approved",
                            "value": {
                                "status": "Y",
                                "authorization_number": "12345678",
                                "authorization_date": "260123",
                                "card_info": {
                                    "SERIAL_NUMBER": "1234567890123456",
                                    "ACQUIRER_ID": "001",
                                    "ACQUIRER_NAME": "신한카드",
                                    "ISSUER_ID": "002",
                                    "ISSUER_NAME": "KB국민카드",
                                    "MERCHANT_ID": "1234567890"
                                },
                                "vankey": "VANKEY1234567890ABCDEFGH",
                                "response_code": 0x00,
                                "message": "Approved"
                            }
                        },
                        "declined": {
                            "summary": "Payment declined",
                            "value": {
                                "status": "N",
                                "authorization_number": None,
                                "authorization_date": "260123",
                                "card_info": None,
                                "vankey": None,
                                "response_code": 0xB2,
                                "message": "Declined - Insufficient funds"
                            }
                        },
                        "timeout": {
                            "summary": "Transaction timeout",
                            "value": {
                                "status": "N",
                                "authorization_number": None,
                                "authorization_date": "260123",
                                "card_info": None,
                                "vankey": None,
                                "response_code": 0xB0,
                                "message": "Transaction timeout"
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Validation error",
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "urn:payment-gateway:error:validation",
                        "title": "Validation Error",
                        "status": 400,
                        "detail": "Amount must be exactly 9 digits",
                        "instance": "/payment/token/approve"
                    }
                }
            }
        }
    }
)
async def approve_token_payment(
    request: Request,
    data: PaymentTokenApproveRequest
) -> PaymentTokenApproveResponse:
    """
    Approve a token payment transaction.

    Example:
        POST /payment/token/approve
        {
            "amount": 10000,
            "tax": 1000,
            "service_fee": 0,
            "approval_number": "12345678"
        }

    Args:
        request: FastAPI request object
        data: Token approval request data

    Returns:
        Token approval response with transaction details

    Raises:
        ValidationError: Invalid request parameters
        CommunicationError: Device communication failure
        TimeoutError: Request timeout
    """
    app_state = get_app_state(request)

    result = await send_tx_token_approve(
        comm=app_state.comm,
        amount=data.amount,
        vankey_hash=data.vankey_hash,
    )

    return PaymentTokenApproveResponse(
        status=result["status"].name,
        authorization_number=result.get("authorization_number"),
        authorization_date="",
        card_info=result.get("card_info"),
        vankey=result.get("vankey"),
        response_code=result["response_code"].value,
        message=result["message"],
    )


@app.post(
    "/payment/token/cancel",
    response_model=PaymentTokenCancelResponse,
    status_code=status.HTTP_200_OK,
    tags=["Token Payment"],
    summary="Cancel token payment",
    description="Cancel a previously approved token payment transaction",
    responses={
        200: {
            "description": "Cancellation approved or declined",
            "content": {
                "application/json": {
                    "examples": {
                        "approved": {
                            "summary": "Cancellation approved",
                            "value": {
                                "status": "Y",
                                "card_info": {
                                    "SERIAL_NUMBER": "1234567890123456",
                                    "ACQUIRER_ID": "001",
                                    "ACQUIRER_NAME": "신한카드",
                                    "ISSUER_ID": "002",
                                    "ISSUER_NAME": "KB국민카드",
                                    "MERCHANT_ID": "MERCHANT001"
                                },
                                "vankey": "VANKEY1234567890ABCDEFGH",
                                "response_code": 0x00,
                                "message": "Cancellation approved"
                            }
                        },
                        "not_found": {
                            "summary": "Original transaction not found",
                            "value": {
                                "status": "N",
                                "card_info": None,
                                "vankey": None,
                                "response_code": 0xB2,
                                "message": "Original transaction not found"
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Validation error",
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "urn:payment-gateway:error:validation",
                        "title": "Validation Error",
                        "status": 400,
                        "detail": "Authorization date must be in YYMMDD format",
                        "instance": "/payment/token/cancel"
                    }
                }
            }
        }
    }
)
async def cancel_token_payment(
    request: Request,
    data: PaymentTokenCancelRequest
) -> PaymentTokenCancelResponse:
    """
    Cancel a token payment transaction.

    Example:
        POST /payment/token/cancel
        {
            "amount": 10000,
            "tax": 1000,
            "service_fee": 0,
            "authorization_number": "12345678",
            "authorization_date": "0101"
        }

    Args:
        request: FastAPI request object
        data: Token cancellation request data

    Returns:
        Token cancellation response

    Raises:
        ValidationError: Invalid request parameters
        CommunicationError: Device communication failure
        TimeoutError: Request timeout
    """
    app_state = get_app_state(request)

    result = await send_tx_token_cancel(
        comm=app_state.comm,
        amount=data.amount,
        original_authorization_number=data.original_authorization_number,
        original_authorization_date=data.original_authorization_date,
        vankey_hash=data.vankey_hash,
    )

    return PaymentTokenCancelResponse(
        status=result["status"].name,
        card_info=result.get("card_info"),
        vankey=result.get("vankey"),
        response_code=result["response_code"].value,
        message=result["message"],
    )


# ============================================================================
# Samsung Pay Endpoints
# ============================================================================


@app.post(
    "/payment/samsung-pay/approve",
    response_model=SamsungPayApproveResponse,
    status_code=status.HTTP_200_OK,
    tags=["Samsung Pay"],
    summary="Approve Samsung Pay payment",
    description="Initiate a Samsung Pay transaction with the CAT device",
    responses={
        200: {
            "description": "Samsung Pay transaction approved or declined",
            "content": {
                "application/json": {
                    "examples": {
                        "approved": {
                            "summary": "Payment approved",
                            "value": {
                                "status": "Y",
                                "authorization_number": "87654321",
                                "authorization_date": "260123",
                                "card_info": {
                                    "SERIAL_NUMBER": "9876543210987654",
                                    "ACQUIRER_ID": "003",
                                    "ACQUIRER_NAME": "우리카드",
                                    "ISSUER_ID": "004",
                                    "ISSUER_NAME": "하나카드",
                                    "MERCHANT_ID": "MERCHANT002"
                                },
                                "vankey": "SPAYKEY98765ABCDEFGH1234",
                                "response_code": 0,
                                "message": "Approved"
                            }
                        },
                        "declined": {
                            "summary": "Payment declined",
                            "value": {
                                "status": "N",
                                "authorization_number": None,
                                "authorization_date": "260123",
                                "card_info": None,
                                "vankey": None,
                                "response_code": 0xB2,
                                "message": "Card declined - Contact issuer"
                            }
                        },
                        "user_cancelled": {
                            "summary": "User cancelled transaction",
                            "value": {
                                "status": "N",
                                "authorization_number": None,
                                "authorization_date": "260123",
                                "card_info": None,
                                "vankey": None,
                                "response_code": 0xB1,
                                "message": "Transaction cancelled by user"
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Validation error",
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "urn:payment-gateway:error:validation",
                        "title": "Validation Error",
                        "status": 400,
                        "detail": "Authorization type must be PRE_AUTH or PURCHASE",
                        "instance": "/payment/samsung-pay/approve"
                    }
                }
            }
        }
    }
)
async def approve_samsung_pay(
    request: Request,
    data: SamsungPayApproveRequest
) -> SamsungPayApproveResponse:
    """
    Approve a Samsung Pay transaction.

    Example:
        POST /payment/samsung-pay/approve
        {
            "amount": 10000,
            "tax": 1000,
            "service_fee": 0,
            "installment": 0
        }

    Args:
        request: FastAPI request object
        data: Samsung Pay approval request data

    Returns:
        Samsung Pay approval response with transaction details

    Raises:
        ValidationError: Invalid request parameters
        CommunicationError: Device communication failure
        TimeoutError: Request timeout
    """
    app_state = get_app_state(request)

    result = await send_tx_spay_approve(
        comm=app_state.comm,
        amount=data.amount,
        authorization_type=AuthorizationType[data.authorization_type],
        display_message=data.display_message or "",
    )

    return SamsungPayApproveResponse(
        status=result["status"].name,
        authorization_number=result.get("authorization_number"),
        authorization_date="",
        card_info=result.get("card_info"),
        vankey=result.get("vankey"),
        response_code=result["response_code"].value,
        message=result["message"],
    )


@app.post(
    "/payment/samsung-pay/cancel",
    response_model=SamsungPayCancelResponse,
    status_code=status.HTTP_200_OK,
    tags=["Samsung Pay"],
    summary="Cancel Samsung Pay payment",
    description="Cancel a previously approved Samsung Pay transaction",
    responses={
        200: {
            "description": "Samsung Pay cancellation approved or declined",
            "content": {
                "application/json": {
                    "examples": {
                        "approved": {
                            "summary": "Cancellation approved",
                            "value": {
                                "status": "Y",
                                "card_info": {
                                    "SERIAL_NUMBER": "9876543210987654",
                                    "ACQUIRER_ID": "003",
                                    "ACQUIRER_NAME": "우리카드",
                                    "ISSUER_ID": "004",
                                    "ISSUER_NAME": "하나카드",
                                    "MERCHANT_ID": "MERCHANT002"
                                },
                                "vankey": "SPAYKEY98765ABCDEFGH1234",
                                "response_code": 0x00,
                                "message": "Cancellation approved"
                            }
                        },
                        "expired": {
                            "summary": "Cancellation period expired",
                            "value": {
                                "status": "N",
                                "card_info": None,
                                "vankey": None,
                                "response_code": 0xB0,
                                "message": "Cancellation period expired"
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Validation error",
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "urn:payment-gateway:error:validation",
                        "title": "Validation Error",
                        "status": 400,
                        "detail": "VAN key must be exactly 24 characters",
                        "instance": "/payment/samsung-pay/cancel"
                    }
                }
            }
        }
    }
)
async def cancel_samsung_pay(
    request: Request,
    data: SamsungPayCancelRequest
) -> SamsungPayCancelResponse:
    """
    Cancel a Samsung Pay transaction.

    Example:
        POST /payment/samsung-pay/cancel
        {
            "amount": 10000,
            "tax": 1000,
            "service_fee": 0,
            "authorization_number": "12345678",
            "authorization_date": "0101"
        }

    Args:
        request: FastAPI request object
        data: Samsung Pay cancellation request data

    Returns:
        Samsung Pay cancellation response

    Raises:
        ValidationError: Invalid request parameters
        CommunicationError: Device communication failure
        TimeoutError: Request timeout
    """
    app_state = get_app_state(request)

    result = await send_tx_spay_cancel(
        comm=app_state.comm,
        amount=data.amount,
        original_authorization_number=data.original_authorization_number,
        original_authorization_date=data.original_authorization_date,
        vankey=data.vankey,
    )

    return SamsungPayCancelResponse(
        status=result["status"].name,
        card_info=result.get("card_info"),
        vankey=result.get("vankey"),
        response_code=result["response_code"].value,
        message=result["message"],
    )


# ============================================================================
# SSE Event Stream
# ============================================================================


@app.get(
    "/sse",
    tags=["Events"],
    summary="SSE event stream",
    description="Server-Sent Events stream for device-initiated events",
    responses={
        200: {
            "description": "text/event-stream with JSON payloads",
            "content": {
                "text/event-stream": {
                    "examples": {
                        "tx_token_generate": {
                            "summary": "Token generated successfully",
                            "value": "event: tx_token_generate\ndata: {\"status\": \"Y\", \"vankey_hash\": \"VANKEY1234567890HASH1234\", \"card_info\": {\"SERIAL_NUMBER\": \"123\", \"ACQUIRER_ID\": \"001\", \"ACQUIRER_NAME\": \"ACQ\", \"ISSUER_ID\": \"002\", \"ISSUER_NAME\": \"ISS\", \"MERCHANT_ID\": \"MERCH\"}, \"response_code\": 0, \"message\": \"Approved\"}\n\n"
                        },
                        "tx_token_generate_error": {
                            "summary": "Token generation failed",
                            "value": "event: tx_token_generate_error\ndata: {\"error\": \"Token generation failed\"}\n\n"
                        },
                        "samsung_pay_init": {
                            "summary": "Samsung Pay initialization",
                            "value": "event: samsung_pay_init\ndata: {}\n\n"
                        },
                        "rfid_init": {
                            "summary": "RFID detected",
                            "value": "event: rfid_init\ndata: {\"data\": \"1234567890\"}\n\n"
                        },
                    }
                }
            },
        }
    },
)
async def event_stream(request: Request) -> StreamingResponse:
    """
    SSE endpoint for device-initiated events.

    Returns a stream of Server-Sent Events for:
    - Token initialization events
    - Samsung Pay initialization events
    - RFID card detection events

    Example events (SSE wire format):
        event: tx_token_generate
        data: {"status": "Y", "vankey_hash": "VANKEY1234567890HASH1234", "card_info": {"SERIAL_NUMBER": "123", "ACQUIRER_ID": "001", "ACQUIRER_NAME": "ACQ", "ISSUER_ID": "002", "ISSUER_NAME": "ISS", "MERCHANT_ID": "MERCH"}, "response_code": 0, "message": "Approved"}

        event: tx_token_generate_error
        data: {"error": "Token generation failed"}

        event: samsung_pay_init
        data: {}

        event: rfid_init
        data: {"data": "1234567890"}

    Args:
        request: FastAPI request object

    Returns:
        SSE stream response
    """
    app_state = get_app_state(request)

    async def event_generator():
        try:
            while not app_state.shutdown_event.is_set():
                # Wait for event with timeout to allow shutdown checking
                try:
                    event = await asyncio.wait_for(
                        app_state.sse_queue.get(),
                        timeout=1.0
                    )
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                except asyncio.TimeoutError:
                    # Check if client disconnected
                    if await request.is_disconnected():
                        break
                    continue
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled")
        finally:
            logger.info("SSE stream closed")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# ============================================================================
# Graceful Server
# ============================================================================


class GracefulServer(Server):
    """
    Uvicorn server with external shutdown event support.

    Extends Uvicorn's Server to monitor an external asyncio.Event for
    graceful shutdown coordination across multiple services.
    """

    def __init__(self, config: Config, shutdown_event: asyncio.Event):
        """
        Initialize graceful server.

        Args:
            config: Uvicorn server configuration
            shutdown_event: External shutdown event to monitor
        """
        super().__init__(config)
        self._external_shutdown = shutdown_event
        self.force_exit = False  # Graceful shutdown, wait for requests

    async def serve(self, sockets=None):
        """
        Override serve to monitor external shutdown event.

        Args:
            sockets: Optional pre-bound sockets
        """
        # Start shutdown monitor task
        monitor_task = asyncio.create_task(self._monitor_shutdown())
        try:
            await super().serve(sockets)
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_shutdown(self):
        """Monitor external shutdown event and trigger server shutdown."""
        await self._external_shutdown.wait()
        logger.info("External shutdown signal received, stopping API server")
        self.should_exit = True

    async def shutdown(self, sockets=None):
        """
        Override shutdown to set external shutdown event.

        Args:
            sockets: Optional pre-bound sockets
        """
        self._external_shutdown.set()
        await super().shutdown(sockets)


# ============================================================================
# Server Initialization
# ============================================================================


async def serve_api(
    comm: Communication,
    sse_queue: asyncio.Queue,
    shutdown_event: asyncio.Event,
    host: str = "0.0.0.0",
    port: int = 5000,
    log_level: str = "info",
):
    """
    Start the FastAPI server with graceful shutdown support.

    Args:
        comm: Communication instance for device interaction
        sse_queue: Queue for publishing SSE events
        shutdown_event: Event to monitor for shutdown signal
        host: Server bind address
        port: Server port
        log_level: Uvicorn log level
    """
    # Initialize application state
    app_state = ApplicationState(
        comm=comm,
        sse_queue=sse_queue,
        shutdown_event=shutdown_event,
    )

    # Store in app.state for dependency injection
    app.state.app_state = app_state

    # Create graceful server
    config = Config(app=app, host=host, port=port, log_level=log_level)
    server = GracefulServer(config=config, shutdown_event=shutdown_event)

    logger.info(f"Starting API server on {host}:{port}")
    await server.serve()
