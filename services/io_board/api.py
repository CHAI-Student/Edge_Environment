"""
FastAPI REST API for IO Board device control.

This module provides a RESTful API interface to the IO Board device with:
- Comprehensive endpoint documentation
- Standard error responses
- Request/response validation
- Structured logging
- Correlation ID tracking
"""

import asyncio
import json
import signal
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError as PydanticValidationError
from uvicorn.config import Config as UvicornConfig
from uvicorn.server import Server

from . import commands
from .config import APIConfig
from .exceptions import IOBoardError, ValidationError
from .logging_config import (
    PerformanceLogger,
    get_logger,
    set_correlation_id,
    clear_correlation_id,
)
from .io_types import (
    DeadboltRequest,
    DeadboltResponse,
    DoorState,
    DoorUpdateEvent,
    ErrorItem,
    ErrorListResponse,
    IOStatusResponse,
    LoadCellsResponse,
    LoadcellChangeEvent,
    LoadcellUncertaintyEvent,
    LoadcellUpdateEvent,
    ManufacturingNumberRequest,
    ManufacturingNumberResponse,
    ProductInfoResponse,
    StandardErrorResponse,
    SuccessResponse,
)
from .filters import FilterMethod, ThresholdScope
from .events import LoadcellChangeDetector

logger = get_logger(__name__)

# Shared shutdown signal for cooperative streaming stop
stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register signal handlers and expose stop flag on app state."""
    loop = asyncio.get_running_loop()

    def _set_stop_event() -> None:
        stop_event.set()

    # Register OS signal handlers where supported
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _set_stop_event)
        except (NotImplementedError, RuntimeError):
            # Windows or non-main thread may not support signal handlers
            pass

    app.state.stop_event = stop_event

    try:
        yield
    finally:
        stop_event.set()


app = FastAPI(
    title="IO Board Control API",
    description="REST API for controlling IO Board device with loadcells, door locks, and sensors",
    version="2.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Middleware for request/response logging with correlation IDs.

    Logs all incoming requests and outgoing responses with timing information
    and correlation IDs for request tracing.
    """
    # Generate correlation ID for this request
    correlation_id = set_correlation_id()

    # Log incoming request
    logger.info(
        f"Request started: method={request.method} path={request.url.path} "
        f"client={request.client.host if request.client else 'unknown'}"
    )

    # Log request body for POST/PUT/PATCH
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.body()
            if body:
                logger.debug(f"Request body: {body.decode('utf-8')}")
        except Exception:
            pass

    # Process request and measure time
    try:
        with PerformanceLogger(logger, "request", path=request.url.path):
            response = await call_next(request)

        # Log response
        logger.info(
            f"Request completed: status={response.status_code}"
        )

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response
    finally:
        clear_correlation_id()


@app.exception_handler(IOBoardError)
async def ioboard_error_handler(request: Request, exc: IOBoardError) -> JSONResponse:
    """
    Global exception handler for IO Board errors.

    Converts all IOBoardError exceptions to standard JSON error responses.
    """
    logger.error(
        f"IO Board error: {exc.error_code.value} - {exc.message}",
        exc_info=exc
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=exc.to_dict(),
    )


@app.exception_handler(PydanticValidationError)
async def validation_error_handler(
    request: Request, exc: PydanticValidationError
) -> JSONResponse:
    """
    Global exception handler for Pydantic validation errors.

    Converts validation errors to standard JSON error responses.
    """
    logger.warning(f"Validation error: {exc.errors()}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "E4001",
            "message": "Request validation failed",
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for unexpected errors.

    Logs the full exception and returns a generic error response
    without leaking internal details.
    """
    logger.error(f"Unexpected error: {exc}", exc_info=exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": "E9001",
            "message": "Internal server error",
            "details": {},
        },
    )


@app.post(
    "/init",
    response_model=SuccessResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Initialize IO Board",
    description="Initialize the IO Board device. Should be called after device power-on or reset.",
    tags=["Device Management"],
)
async def handle_init() -> SuccessResponse:
    """Initialize the IO Board device."""
    await commands.initialize()
    return SuccessResponse(message="IO Board initialized successfully")


@app.post(
    "/deadbolt",
    response_model=DeadboltResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Control door deadbolt",
    description="Open or close the door deadbolt lock. Returns the actual state after command execution.",
    tags=["Door Control"],
)
async def handle_deadbolt(request: DeadboltRequest) -> DeadboltResponse:
    """
    Control door deadbolt lock.

    Args:
        request: Deadbolt control request with desired state

    Returns:
        Current deadbolt state after command execution
    """
    result_state = await commands.set_door_state(request.state)

    # Also get full IO status to verify deadbolt state
    io_status = await commands.get_io_status()
    logger.info(f"IO status after deadbolt command: {io_status}")

    # Return state based on deadbolt sensor reading
    if "OPEN" in io_status["deadbolt"].upper():
        return DeadboltResponse(state=DoorState.OPEN)
    else:
        return DeadboltResponse(state=DoorState.CLOSE)


@app.post(
    "/calibrate",
    response_model=SuccessResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Calibrate sensors",
    description="Calibrate all loadcell weight sensors. Device should be unloaded before calibration.",
    tags=["Device Management"],
)
async def handle_calibrate() -> SuccessResponse:
    """Calibrate IO Board sensors."""
    await commands.calibrate()
    return SuccessResponse(message="Calibration completed successfully")


@app.post(
    "/manufacturing_number",
    response_model=ManufacturingNumberResponse,
    responses={
        422: {"description": "Invalid manufacturing number format"},
        500: {"model": StandardErrorResponse, "description": "Device or communication error"},
    },
    summary="Set manufacturing number",
    description="Set the device manufacturing/product ID (11 alphanumeric characters).",
    tags=["Device Management"],
)
async def handle_manufacturing_number(
    request: ManufacturingNumberRequest,
) -> ManufacturingNumberResponse:
    """
    Set device manufacturing number.

    Args:
        request: Manufacturing number (11 characters)

    Returns:
        Manufacturing number as confirmed by device
    """
    result = await commands.set_manufacturing_number(request.manufacturing_number)
    return ManufacturingNumberResponse(manufacturing_number=result)


@app.delete(
    "/errors",
    response_model=SuccessResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Clear error log",
    description="Clear all error codes from the device error history.",
    tags=["Device Management"],
)
async def handle_clear_errors() -> SuccessResponse:
    """Clear device error log."""
    await commands.clear_errors()
    return SuccessResponse(message="Error log cleared successfully")


@app.post(
    "/reboot",
    response_model=SuccessResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Reboot device",
    description="Reboot the IO Board device (hard reboot via relay with timer). Device will be unavailable during restart and may not reply due to power interrupt.",
    tags=["Device Management"],
)
async def handle_reboot() -> SuccessResponse:
    """Reboot IO Board device (hard reboot via relay with timer). Device may not reply due to power interrupt."""
    await commands.reboot()
    return SuccessResponse(message="Device reboot initiated")


@app.get(
    "/product_info",
    response_model=ProductInfoResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Get product information",
    description="Retrieve device manufacturing information including product ID and software version.",
    tags=["Device Information"],
)
async def handle_product_info() -> ProductInfoResponse:
    """Get device product information."""
    info = await commands.get_product_info()
    return ProductInfoResponse(
        product_id=info["product_id"],
        sw_version=info["sw_version"],
    )


@app.get(
    "/loadcells",
    response_model=LoadCellsResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Get loadcell readings",
    description="Get current weight readings from all 10 loadcell sensors.",
    tags=["Sensors"],
)
async def handle_loadcells() -> LoadCellsResponse:
    """Get loadcell weight readings."""
    loadcells = await commands.get_loadcells()
    return LoadCellsResponse(loadcells=loadcells)


@app.get(
    "/health",
    summary="Health check",
    description="Health check endpoint for Docker healthcheck and service monitoring.",
    tags=["System"],
)
async def health_check():
    """Health check endpoint matching Node.js format."""
    return {
        "status": "healthy",
        "service": "io_board",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get(
    "/status",
    response_model=IOStatusResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Get IO status",
    description="Get current status of door and deadbolt sensors.",
    tags=["Sensors"],
)
async def handle_status() -> IOStatusResponse:
    """Get door and deadbolt IO status."""
    io_status = await commands.get_io_status()
    return IOStatusResponse(
        door=io_status["door"],
        deadbolt=io_status["deadbolt"],
    )


@app.get(
    "/errors",
    response_model=ErrorListResponse,
    responses={
        500: {"model": StandardErrorResponse, "description": "Device or communication error"}
    },
    summary="Get error list",
    description="Retrieve device error history (up to 4 error codes).",
    tags=["Device Information"],
)
async def handle_errors() -> ErrorListResponse:
    """Get device error history."""
    errors = await commands.get_errors()
    return ErrorListResponse(
        errors=[ErrorItem(code=err) for err in errors]
    )


@app.get(
    "/stream/loadcells",
    responses={
        200: {
            "description": "Server-Sent Events stream of loadcell data",
            "content": {"text/event-stream": {}},
        }
    },
    summary="Stream loadcell readings (DEPRECATED)",
    description="DEPRECATED: Use /sse?streams=loadcells instead. Server-Sent Events (SSE) stream of real-time loadcell weight readings.",
    tags=["Sensors"],
    deprecated=True,
)
async def handle_stream_loadcells(request: Request) -> StreamingResponse:
    """
    Stream loadcell readings via Server-Sent Events.

    DEPRECATED: This endpoint is deprecated. Use the unified /sse endpoint instead:
    GET /sse?streams=loadcells&loadcell_interval=0.5

    Continuously sends loadcell readings as SSE events. Stream terminates
    when client disconnects or server shuts down.
    """
    logger.warning("Deprecated endpoint /stream/loadcells accessed. Use /sse?streams=loadcells instead.")
    async def event_generator():
        """Generate SSE events with loadcell data."""
        # Get stream interval from app state
        stream_interval = app.state.stream_interval
        stop_flag = app.state.stop_event

        logger.info("Started loadcell SSE stream")
        try:
            while not stop_flag.is_set():
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("Client disconnected from loadcell stream")
                    break

                try:
                    loadcells = await commands.get_loadcells()
                    data = json.dumps({"loadcells": loadcells})
                    yield f"event: update\ndata: {data}\n\n"
                except asyncio.CancelledError:
                    logger.info("Loadcell SSE stream cancelled")
                    raise
                except IOBoardError as e:
                    # Send error event but don't terminate stream
                    error_data = json.dumps(e.to_dict())
                    yield f"event: error\ndata: {error_data}\n\n"
                    logger.warning(f"Error in loadcell stream: {e}")
                except Exception as e:
                    # Unexpected error - log and send generic error event
                    logger.error(f"Unexpected error in loadcell stream: {e}", exc_info=e)
                    error_data = json.dumps({
                        "error_code": "E9001",
                        "message": "Stream error occurred",
                        "details": {}
                    })
                    yield f"event: error\ndata: {error_data}\n\n"

                await asyncio.sleep(stream_interval)
        finally:
            logger.info("Loadcell SSE stream ended")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get(
    "/sse",
    responses={
        200: {
            "description": "Unified Server-Sent Events stream with 5 event types",
            "content": {"text/event-stream": {}},
        },
        422: {"model": StandardErrorResponse, "description": "Invalid parameters"},
    },
    response_model=None,
    summary="Unified SSE stream for loadcells and door status",
    description="""Server-Sent Events stream with configurable data sources and filtering.

    **Event Types:**
    - `loadcell.update`: Periodic loadcell readings (filtered and raw)
    - `loadcell.change`: Threshold breach detection events
    - `loadcell.uncertainty`: Error states or parse failures (anti-theft)
    - `door.update`: Periodic door/deadbolt status
    - `error`: Stream-level errors

    **Example Usage:**
    - Single stream: `/sse?streams=loadcells&loadcell_interval=0.5`
    - Dual stream: `/sse?streams=loadcells,doors&loadcell_interval=0.2&door_interval=1.0`
    - With filtering: `/sse?streams=loadcells&filter_method=exponential&filter_alpha=0.3`
    - With thresholds: `/sse?streams=loadcells&threshold=10.0&threshold_scope=filtered`
    """,
    tags=["Streaming"],
)
async def handle_unified_sse(
    request: Request,
    streams: str = Query(
        ...,
        description="Comma-separated list of streams to enable (loadcells, doors)",
        example="loadcells,doors"
    ),
    loadcell_interval: float = Query(
        default=0.5,
        ge=0.1,
        le=10.0,
        description="Polling interval for loadcell updates in seconds (minimum 0.1s)",
        example=0.5
    ),
    door_interval: float = Query(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Polling interval for door status updates in seconds (minimum 0.1s)",
        example=1.0
    ),
    filter_method: FilterMethod = Query(
        default=FilterMethod.NONE,
        description="Filtering method for loadcell values (none, exponential, kalman)",
        example="exponential"
    ),
    filter_alpha: float = Query(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Alpha parameter for exponential smoothing (0.0=max smoothing, 1.0=no smoothing)",
        example=0.3
    ),
    filter_q: float = Query(
        default=0.001,
        gt=0.0,
        description="Process noise covariance (Q) for Kalman filter",
        example=0.001
    ),
    filter_r: float = Query(
        default=1.0,
        gt=0.0,
        description="Measurement noise covariance (R) for Kalman filter",
        example=1.0
    ),
    threshold: str = Query(
        default="0.0",
        description="Threshold for change detection. Single value (broadcast to all 10) or comma-separated list of 10 values",
        example="5.0"
    ),
    threshold_scope: ThresholdScope = Query(
        default=ThresholdScope.FILTERED,
        description="Apply threshold to raw or filtered values",
        example="filtered"
    ),
) -> JSONResponse | StreamingResponse:
    """
    Unified SSE endpoint for streaming loadcell and door status.

    Supports multiple concurrent data streams with independent intervals,
    configurable filtering, and threshold-based change detection.
    """
    # Parse and validate streams parameter
    enabled_streams = [s.strip() for s in streams.split(",") if s.strip()]
    valid_streams = {"loadcells", "doors"}
    invalid_streams = set(enabled_streams) - valid_streams

    if not enabled_streams:
        logger.error("Empty streams parameter provided")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "E4002",
                "message": "At least one stream must be specified",
                "details": {"valid_streams": list(valid_streams)}
            }
        )

    if invalid_streams:
        logger.error(f"Invalid stream names: {invalid_streams}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "E4003",
                "message": f"Invalid stream names: {', '.join(invalid_streams)}",
                "details": {"valid_streams": list(valid_streams), "invalid_streams": list(invalid_streams)}
            }
        )

    # Parse threshold parameter
    threshold_values = []
    threshold_parts = [t.strip() for t in threshold.split(",") if t.strip()]

    if len(threshold_parts) == 1:
        # Single value - broadcast to all 10 loadcells
        try:
            single_threshold = float(threshold_parts[0])
            threshold_values = [single_threshold] * 10
        except ValueError:
            logger.error(f"Invalid threshold value: {threshold_parts[0]}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error_code": "E4004",
                    "message": "Threshold must be a valid number",
                    "details": {"provided": threshold_parts[0]}
                }
            )
    elif len(threshold_parts) == 10:
        # Per-loadcell thresholds
        try:
            threshold_values = [float(t) for t in threshold_parts]
        except ValueError as e:
            logger.error(f"Invalid threshold values: {e}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error_code": "E4005",
                    "message": "All threshold values must be valid numbers",
                    "details": {"provided": threshold_parts}
                }
            )
    else:
        logger.error(f"Invalid threshold count: {len(threshold_parts)} (expected 1 or 10)")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "E4006",
                "message": "Threshold must be a single value or exactly 10 comma-separated values",
                "details": {"provided_count": len(threshold_parts), "expected": "1 or 10"}
            }
        )

    logger.info(
        f"Starting unified SSE stream: streams={enabled_streams} "
        f"loadcell_interval={loadcell_interval} door_interval={door_interval} "
        f"filter_method={filter_method} threshold_scope={threshold_scope}"
    )

    async def unified_event_generator():
        """Generate multiplexed SSE events from enabled streams."""
        stop_flag = app.state.stop_event
        event_queue = asyncio.Queue()
        tasks = []

        # Create change detector if loadcells stream enabled
        detector = None
        if "loadcells" in enabled_streams:
            detector = LoadcellChangeDetector(
                filter_method=filter_method,
                thresholds=threshold_values,
                threshold_scope=threshold_scope,
                alpha=filter_alpha,
                q=filter_q,
                r=filter_r
            )

        async def poll_loadcells():
            """Poll loadcell data and generate events."""
            nonlocal detector
            if not detector:
                return
            while not stop_flag.is_set():
                if await request.is_disconnected():
                    break

                try:
                    raw_values = await commands.get_loadcells()
                    timestamp = datetime.utcnow().isoformat()

                    # Process values through detector
                    filtered_strings, filtered_numerics, changed_indices, change_details = detector.process(raw_values)

                    # Check for uncertainties
                    uncertain_indices = detector.detect_uncertainties(raw_values, filtered_numerics)

                    # Always send update event
                    update_event = LoadcellUpdateEvent(
                        timestamp=timestamp,
                        raw_values=raw_values,
                        filtered_values=filtered_strings,
                        filter_method=filter_method.value
                    )
                    await event_queue.put(("loadcell.update", update_event.model_dump()))

                    # Send change event if threshold exceeded
                    if changed_indices:
                        change_event = LoadcellChangeEvent(
                            timestamp=timestamp,
                            changed_indices=changed_indices,
                            old_values=change_details["old_values"],
                            new_values=change_details["new_values"],
                            deltas=change_details["deltas"],
                            threshold=threshold_values[0] if len(set(threshold_values)) == 1 else threshold_values,
                            threshold_scope=threshold_scope.value
                        )
                        await event_queue.put(("loadcell.change", change_event.model_dump()))

                    # Send uncertainty event if errors detected
                    if uncertain_indices:
                        error_values = [raw_values[i] for i in uncertain_indices]
                        uncertainty_event = LoadcellUncertaintyEvent(
                            timestamp=timestamp,
                            affected_indices=uncertain_indices,
                            reason="error_state",
                            details={"error_values": error_values}
                        )
                        await event_queue.put(("loadcell.uncertainty", uncertainty_event.model_dump()))
                except asyncio.CancelledError:
                    logger.info("Loadcell polling cancelled")
                    raise
                except IOBoardError as e:
                    # I/O board failure - reset filter state and send uncertainty for all loadcells
                    if detector:
                        detector.reset()

                    timestamp = datetime.utcnow().isoformat()
                    uncertainty_event = LoadcellUncertaintyEvent(
                        timestamp=timestamp,
                        affected_indices=list(range(10)),
                        reason="io_board_failure",
                        details=e.to_dict()
                    )
                    await event_queue.put(("loadcell.uncertainty", uncertainty_event.model_dump()))

                    # Also send error event
                    await event_queue.put(("error", {"stream": "loadcells", **e.to_dict()}))
                    logger.warning(f"Loadcell stream error: {e}")

                except Exception as e:
                    # Unexpected error
                    logger.error(f"Unexpected error in loadcell stream: {e}", exc_info=e)
                    await event_queue.put(("error", {
                        "stream": "loadcells",
                        "error_code": "E9002",
                        "message": "Unexpected loadcell stream error",
                        "details": {}
                    }))

                await asyncio.sleep(loadcell_interval)

        async def poll_doors():
            """Poll door status and generate events."""
            while not stop_flag.is_set():
                if await request.is_disconnected():
                    break

                try:
                    io_status = await commands.get_io_status()
                    timestamp = datetime.utcnow().isoformat()

                    door_event = DoorUpdateEvent(
                        timestamp=timestamp,
                        door=io_status["door"],
                        deadbolt=io_status["deadbolt"]
                    )
                    await event_queue.put(("door.update", door_event.model_dump()))
                except asyncio.CancelledError:
                    logger.info("Door polling cancelled")
                    raise
                except IOBoardError as e:
                    # Send error event but don't terminate
                    await event_queue.put(("error", {"stream": "doors", **e.to_dict()}))
                    logger.warning(f"Door stream error: {e}")

                except Exception as e:
                    logger.error(f"Unexpected error in door stream: {e}", exc_info=e)
                    await event_queue.put(("error", {
                        "stream": "doors",
                        "error_code": "E9003",
                        "message": "Unexpected door stream error",
                        "details": {}
                    }))

                await asyncio.sleep(door_interval)

        # Start polling tasks for enabled streams
        if "loadcells" in enabled_streams:
            tasks.append(asyncio.create_task(poll_loadcells()))
        if "doors" in enabled_streams:
            tasks.append(asyncio.create_task(poll_doors()))

        try:
            # Consume events from queue and yield SSE formatted data
            while not stop_flag.is_set():
                if await request.is_disconnected():
                    logger.info("Client disconnected from unified SSE stream")
                    break

                # Wait for next event with timeout to check disconnect status
                try:
                    event_name, event_data = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    yield f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"
                except asyncio.TimeoutError:
                    # No event available, continue to check disconnect
                    continue
                except asyncio.CancelledError:
                    logger.info("Unified SSE generator cancelled")
                    raise

        finally:
            # Cancel all polling tasks
            for task in tasks:
                task.cancel()

            # Wait for tasks to complete cancellation
            await asyncio.gather(*tasks, return_exceptions=True)

            logger.info(f"Unified SSE stream ended: streams={enabled_streams}")

    return StreamingResponse(
        unified_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def serve_api(config: APIConfig) -> None:
    """
    Start the FastAPI server.

    Args:
        config: API configuration object
    """
    # Store config in app state for access by handlers
    app.state.stream_interval = config.stream_interval

    logger.info(
        f"Starting API server: host={config.host} port={config.port} "
        f"log_level={config.log_level}"
    )

    uvicorn_config = UvicornConfig(
        app=app,
        host=config.host,
        port=config.port,
        log_level=config.log_level,
    )
    server = Server(uvicorn_config)
    server.force_exit = True

    async def watch_for_exit():
        """Set stop flag when uvicorn begins shutdown."""
        # Wait until server signals shutdown (SIGINT/SIGTERM sets should_exit)
        while not server.should_exit:
            await asyncio.sleep(0.2)
        stop_event.set()

    watcher = asyncio.create_task(watch_for_exit())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        with suppress(Exception):
            await watcher
