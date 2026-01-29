"""
Payment gateway application with TCP and REST API.

Enterprise-grade payment gateway supporting:
- TCP server for CAT device communication
- REST API for payment operations
- Real-time SSE event stream
- Graceful shutdown with Windows signal support
- Configurable timeouts and logging

Configuration via environment variables (see core/config.py).
"""

import asyncio
import signal
import sys
from typing import Optional, Set

from action.manager import Action
from api.manager import serve_api
from core.config import Settings
from core.logging_config import get_logger, setup_logging
from payment import Communication

logger = get_logger(__name__)

# Global state for graceful shutdown (required for signal handlers)
_shutdown_event: Optional[asyncio.Event] = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None
_tasks: Set[asyncio.Task] = set()


def _signal_handler(signum: int, frame) -> None:
    """
    Handle shutdown signals (SIGINT, SIGTERM, SIGBREAK).

    Thread-safe callback to set shutdown event from signal context.
    Works on both Windows and Unix systems.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    logger.info(f"Received {sig_name} (signal {signum}), initiating shutdown...")

    logger.info("Current tasks: %s", [task.get_name() for task in asyncio.all_tasks(loop=_main_loop)])

    if _main_loop is not None and _shutdown_event is not None:
        # Thread-safe: schedule event.set() in the event loop
        _main_loop.call_soon_threadsafe(_shutdown_event.set)


def setup_signal_handlers() -> None:
    """
    Setup signal handlers for graceful shutdown.

    Installs handlers for:
    - SIGINT (Ctrl+C) - all platforms
    - SIGTERM (termination request) - Unix primary, Windows rare
    - SIGBREAK (Ctrl+Break) - Windows only

    Uses signal.signal() instead of asyncio.add_signal_handler()
    because the latter doesn't work on Windows.
    """
    # SIGINT: Ctrl+C (all platforms)
    signal.signal(signal.SIGINT, _signal_handler)

    # SIGTERM: termination request
    signal.signal(signal.SIGTERM, _signal_handler)

    # SIGBREAK: Ctrl+Break (Windows only)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _signal_handler)
        logger.info("Signal handlers installed (Windows: SIGINT, SIGTERM, SIGBREAK)")
    else:
        logger.info("Signal handlers installed (Unix: SIGINT, SIGTERM)")


async def run_cat_server(
    settings: Settings,
    comm: Communication,
    shutdown_event: asyncio.Event,
) -> None:
    """
    Run the TCP server for CAT device communication.

    Args:
        settings: Application settings
        comm: Communication instance
        shutdown_event: Event to monitor for shutdown signal
    """
    server = await asyncio.start_server(
        comm.run,
        settings.cat.host,
        settings.cat.port,
    )
    logger.info(f"CAT server listening on {settings.cat.host}:{settings.cat.port}")

    async with server:
        # Serve until shutdown event
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        serve_task = asyncio.create_task(server.serve_forever())

        done, pending = await asyncio.wait(
            [shutdown_task, serve_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        server.close()
        # close_clients() is only available in Python 3.13+
        if hasattr(server, 'close_clients'):
            server.close_clients()

        # Cancel remaining tasks
        for task in pending:
            logger.info("Cancelling CAT server task...")
            try:
                await task
            except asyncio.CancelledError:
                pass

        await server.wait_closed()

    logger.info("CAT server stopped")


async def run_action_manager(
    comm: Communication,
    sse_queue: asyncio.Queue,
    shutdown_event: asyncio.Event,
) -> None:
    """
    Run the action manager for processing device events.

    Args:
        comm: Communication instance
        sse_queue: Queue for SSE events
        shutdown_event: Event to monitor for shutdown signal
    """
    action_manager = Action(comm, sse_queue, shutdown_event)

    # Run action manager with shutdown awareness
    action_task = asyncio.create_task(action_manager.run())
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    done, pending = await asyncio.wait(
        [action_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Call shutdown method for cleanup
    await action_manager.shutdown()

    logger.info("Action manager stopped")


async def run_api_server(
    settings: Settings,
    comm: Communication,
    sse_queue: asyncio.Queue,
    shutdown_event: asyncio.Event,
) -> None:
    """
    Run the FastAPI REST server with shutdown coordination.

    Args:
        settings: Application settings
        comm: Communication instance
        sse_queue: Queue for SSE events
        shutdown_event: Event to monitor for shutdown signal
    """
    await serve_api(
        comm=comm,
        sse_queue=sse_queue,
        shutdown_event=shutdown_event,
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.api.log_level,
    )
    logger.info("API server stopped")


async def graceful_shutdown(settings: Settings, timeout_seconds: float | None = None) -> None:
    """
    Cancel all tracked tasks and wait for completion.

    Args:
        settings: Application settings
        timeout_seconds: Timeout in seconds (uses settings.shutdown_timeout if None)
    """
    if timeout_seconds is None:
        timeout_seconds = settings.shutdown_timeout

    logger.info(f"Graceful shutdown: cancelling {len(_tasks)} tasks...")

    # Cancel all tasks
    for task in _tasks:
        if not task.done():
            task.cancel()

    # Wait for all tasks with timeout
    if _tasks:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*_tasks, return_exceptions=True),
                timeout=timeout_seconds,
            )

            # Log any exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.error(f"Task {i} raised exception during shutdown: {result}")

        except asyncio.TimeoutError:
            logger.warning(
                f"Shutdown timeout after {timeout_seconds}s, "
                f"{sum(1 for t in _tasks if not t.done())} tasks still running"
            )

    logger.info("All tasks completed")


async def main() -> None:
    """Main application entry point."""
    global _shutdown_event, _main_loop, _tasks

    # Load settings
    settings = Settings()

    # Configure logging
    setup_logging(settings.api.log_level.upper())

    logger.info("=" * 70)
    logger.info("Starting Payment Gateway Application")
    logger.info(f"Configuration: API={settings.api.host}:{settings.api.port}, "
                f"CAT={settings.cat.host}:{settings.cat.port}")
    logger.info(f"Timeouts: comm={settings.comm_timeout}s, shutdown={settings.shutdown_timeout}s")
    logger.info("=" * 70)

    # Get event loop reference for signal handler
    _main_loop = asyncio.get_running_loop()
    _shutdown_event = asyncio.Event()

    # Setup signal handlers (must be done from main thread)
    setup_signal_handlers()

    # Create shared communication instance
    comm = Communication()

    # Create SSE queue for action manager
    sse_queue = asyncio.Queue()

    # Create tasks with shutdown event
    cat_task = asyncio.create_task(
        run_cat_server(settings, comm, _shutdown_event),
        name="cat_server"
    )
    _tasks.add(cat_task)

    action_task = asyncio.create_task(
        run_action_manager(comm, sse_queue, _shutdown_event),
        name="action_manager"
    )
    _tasks.add(action_task)

    api_task = asyncio.create_task(
        run_api_server(settings, comm, sse_queue, _shutdown_event),
        name="api_server"
    )
    _tasks.add(api_task)

    logger.info("All services started, waiting for shutdown signal...")

    try:
        # Wait for all tasks to complete (they exit when shutdown_event is set)
        results = await asyncio.gather(*_tasks, return_exceptions=True)

        # Log any exceptions from tasks
        for task_name, result in zip(["CAT server", "Action manager", "API server"], results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.error(f"{task_name} raised exception: {result}", exc_info=result)

    except asyncio.CancelledError:
        logger.info("Main task cancelled")

    finally:
        await graceful_shutdown(settings)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This catches Ctrl+C if signal handler didn't catch it
        logger.info("KeyboardInterrupt received (fallback)")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Payment Gateway Application terminated")
