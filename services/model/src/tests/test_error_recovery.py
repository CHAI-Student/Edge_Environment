"""
Error Recovery Module Tests.

Tests for:
- ErrorCode enum and error messages
- ServiceError creation and serialization
- RecoveryManager health monitoring
- Service recovery handlers
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from error_recovery import (
    RecoveryManager,
    RecoveryStatus,
    ErrorCode,
    ServiceError,
)
from error_recovery.error_codes import ERROR_RECOVERABLE, ERROR_MESSAGES


class TestErrorCode:
    """ErrorCode enum tests."""

    def test_io_board_error_codes(self):
        """Test IO Board error codes (E2xxx)."""
        assert ErrorCode.E2001.value == "E2001"  # Serial port not found
        assert ErrorCode.E2002.value == "E2002"  # Access denied
        assert ErrorCode.E2003.value == "E2003"  # Communication error
        assert ErrorCode.E2004.value == "E2004"  # Checksum error
        assert ErrorCode.E2005.value == "E2005"  # Timeout
        assert ErrorCode.E2006.value == "E2006"  # LoadCell anomaly
        assert ErrorCode.E2007.value == "E2007"  # Deadbolt control fail

    def test_camera_error_codes(self):
        """Test Camera error codes (E3xxx)."""
        assert ErrorCode.E3001.value == "E3001"  # Connection failed
        assert ErrorCode.E3002.value == "E3002"  # Frame capture failed
        assert ErrorCode.E3003.value == "E3003"  # Timeout
        assert ErrorCode.E3004.value == "E3004"  # Decode failed
        assert ErrorCode.E3005.value == "E3005"  # Service unavailable
        assert ErrorCode.E3006.value == "E3006"  # Mapping failed

    def test_vision_error_codes(self):
        """Test Vision error codes (E4xxx)."""
        assert ErrorCode.E4001.value == "E4001"  # Model load failed
        assert ErrorCode.E4002.value == "E4002"  # Inference failed
        assert ErrorCode.E4003.value == "E4003"  # Hand detection failed
        assert ErrorCode.E4004.value == "E4004"  # Product detection failed
        assert ErrorCode.E4005.value == "E4005"  # Ensemble failed

    def test_network_error_codes(self):
        """Test Network error codes (E5xxx)."""
        assert ErrorCode.E5001.value == "E5001"  # SSE connection failed
        assert ErrorCode.E5002.value == "E5002"  # HTTP request failed
        assert ErrorCode.E5003.value == "E5003"  # Node.js connection failed
        assert ErrorCode.E5004.value == "E5004"  # MQTT connection failed
        assert ErrorCode.E5005.value == "E5005"  # Timeout

    def test_payment_error_codes(self):
        """Test Payment error codes (E6xxx)."""
        assert ErrorCode.E6001.value == "E6001"  # Terminal connection failed
        assert ErrorCode.E6002.value == "E6002"  # Approval failed
        assert ErrorCode.E6003.value == "E6003"  # Cancel failed
        assert ErrorCode.E6004.value == "E6004"  # Network error


class TestErrorRecoverable:
    """Error recoverable flag tests."""

    def test_io_board_recoverable(self):
        """Test IO Board error recoverable flags."""
        assert ERROR_RECOVERABLE[ErrorCode.E2001] is False  # Port not found
        assert ERROR_RECOVERABLE[ErrorCode.E2002] is False  # Access denied
        assert ERROR_RECOVERABLE[ErrorCode.E2003] is True   # Communication
        assert ERROR_RECOVERABLE[ErrorCode.E2004] is True   # Checksum
        assert ERROR_RECOVERABLE[ErrorCode.E2005] is True   # Timeout

    def test_camera_recoverable(self):
        """Test Camera error recoverable flags."""
        assert ERROR_RECOVERABLE[ErrorCode.E3001] is True  # Connection
        assert ERROR_RECOVERABLE[ErrorCode.E3002] is True  # Frame capture
        assert ERROR_RECOVERABLE[ErrorCode.E3003] is True  # Timeout
        assert ERROR_RECOVERABLE[ErrorCode.E3006] is True  # Mapping

    def test_vision_recoverable(self):
        """Test Vision error recoverable flags."""
        assert ERROR_RECOVERABLE[ErrorCode.E4001] is False  # Model load
        assert ERROR_RECOVERABLE[ErrorCode.E4002] is True   # Inference

    def test_payment_recoverable(self):
        """Test Payment error recoverable flags."""
        assert ERROR_RECOVERABLE[ErrorCode.E6001] is True   # Terminal
        assert ERROR_RECOVERABLE[ErrorCode.E6002] is False  # Approval
        assert ERROR_RECOVERABLE[ErrorCode.E6003] is False  # Cancel


class TestErrorMessages:
    """Error message tests."""

    def test_error_messages_exist(self):
        """Test all error codes have messages."""
        for code in [
            ErrorCode.E2001, ErrorCode.E2005, ErrorCode.E2006,
            ErrorCode.E3001, ErrorCode.E3002, ErrorCode.E3006,
            ErrorCode.E4001, ErrorCode.E4002,
            ErrorCode.E5001, ErrorCode.E5003,
            ErrorCode.E6001, ErrorCode.E6002,
        ]:
            assert code in ERROR_MESSAGES
            assert len(ERROR_MESSAGES[code]) > 0


class TestServiceError:
    """ServiceError dataclass tests."""

    def test_create_service_error(self):
        """Test ServiceError.create factory."""
        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
        )

        assert error.code == ErrorCode.E3001
        assert error.service == "camera"
        assert error.message == ERROR_MESSAGES[ErrorCode.E3001]
        assert error.recoverable is True
        assert error.timestamp > 0

    def test_create_with_details(self):
        """Test ServiceError with details."""
        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
            details={"camera_id": 1, "zone": 0},
        )

        assert error.details["camera_id"] == 1
        assert error.details["zone"] == 0

    def test_create_with_custom_message(self):
        """Test ServiceError with custom message."""
        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
            message="Custom: Camera 1 disconnected",
        )

        assert error.message == "Custom: Camera 1 disconnected"

    def test_to_dict(self):
        """Test ServiceError serialization."""
        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
            details={"camera_id": 1},
        )

        data = error.to_dict()

        assert data["code"] == "E3001"
        assert data["service"] == "camera"
        assert data["details"] == {"camera_id": 1}
        assert data["recoverable"] is True
        assert "timestamp" in data
        assert "recovery_attempted" in data
        assert "recovery_success" in data


class TestRecoveryStatus:
    """RecoveryStatus enum tests."""

    def test_status_values(self):
        """Test RecoveryStatus values."""
        assert RecoveryStatus.HEALTHY.value == "healthy"
        assert RecoveryStatus.DEGRADED.value == "degraded"
        assert RecoveryStatus.RECOVERING.value == "recovering"
        assert RecoveryStatus.FAILED.value == "failed"


class TestRecoveryManager:
    """RecoveryManager tests."""

    @pytest.fixture
    def manager(self):
        """Fresh RecoveryManager instance."""
        return RecoveryManager(
            max_error_history=50,
            health_check_interval=10.0,
            auto_recovery=True,
        )

    def test_init_default_values(self):
        """Test RecoveryManager initialization."""
        manager = RecoveryManager()

        assert manager.max_error_history == 100
        assert manager.health_check_interval == 30.0
        assert manager.auto_recovery is True

    def test_register_service(self, manager):
        """Test registering a service."""
        manager.register_service("camera")

        assert "camera" in manager._services
        status = manager.get_service_status("camera")
        assert status is not None
        assert status.status == RecoveryStatus.HEALTHY

    def test_register_service_with_handler(self, manager):
        """Test registering service with recovery handler."""
        handler = MagicMock(return_value=True)
        manager.register_service("camera", recovery_handler=handler)

        assert "camera" in manager._recovery_handlers
        assert manager._recovery_handlers["camera"] is handler

    def test_record_error_updates_service(self, manager):
        """Test recording error updates service status."""
        manager.register_service("camera")

        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
        )
        manager.record_error(error)

        status = manager.get_service_status("camera")
        assert status.error_count == 1
        assert status.last_error == error
        assert status.status == RecoveryStatus.DEGRADED

    def test_record_non_recoverable_error(self, manager):
        """Test recording non-recoverable error sets FAILED status."""
        manager.register_service("vision")

        error = ServiceError.create(
            code=ErrorCode.E4001,  # Model load failed - not recoverable
            service="vision",
        )
        manager.record_error(error)

        status = manager.get_service_status("vision")
        assert status.status == RecoveryStatus.FAILED

    def test_get_overall_status_healthy(self, manager):
        """Test overall status when all healthy."""
        manager.register_service("camera")
        manager.register_service("io_board")

        status = manager.get_overall_status()
        assert status == RecoveryStatus.HEALTHY

    def test_get_overall_status_degraded(self, manager):
        """Test overall status with degraded service."""
        manager.register_service("camera")
        manager.register_service("io_board")

        error = ServiceError.create(code=ErrorCode.E3001, service="camera")
        manager.record_error(error)

        status = manager.get_overall_status()
        assert status == RecoveryStatus.DEGRADED

    def test_get_overall_status_failed(self, manager):
        """Test overall status with failed service."""
        manager.register_service("camera")
        manager.register_service("vision")

        error = ServiceError.create(code=ErrorCode.E4001, service="vision")
        manager.record_error(error)

        status = manager.get_overall_status()
        assert status == RecoveryStatus.FAILED

    def test_get_all_status(self, manager):
        """Test getting all services status."""
        manager.register_service("camera")
        manager.register_service("io_board")

        all_status = manager.get_all_status()

        assert "camera" in all_status
        assert "io_board" in all_status
        assert all_status["camera"]["status"] == "healthy"

    def test_get_error_history(self, manager):
        """Test getting error history."""
        manager.register_service("camera")

        for i in range(10):
            error = ServiceError.create(
                code=ErrorCode.E3001,
                service="camera",
                message=f"Error {i}",
            )
            manager.record_error(error)

        history = manager.get_error_history(limit=5)

        assert len(history) == 5
        # Most recent errors
        assert "Error 9" in history[-1]["message"]

    def test_clear_error_history(self, manager):
        """Test clearing error history."""
        manager.register_service("camera")

        error = ServiceError.create(code=ErrorCode.E3001, service="camera")
        manager.record_error(error)

        manager.clear_error_history()

        assert len(manager.get_error_history()) == 0

    def test_error_history_max_size(self, manager):
        """Test error history respects max size."""
        manager.register_service("camera")

        for i in range(100):
            error = ServiceError.create(
                code=ErrorCode.E3001,
                service="camera",
                message=f"Error {i}",
            )
            manager.record_error(error)

        history = manager.get_error_history(limit=200)
        assert len(history) <= manager.max_error_history


class TestRecoveryManagerAsync:
    """RecoveryManager async method tests."""

    @pytest.fixture
    def manager(self):
        """RecoveryManager with mocked clients."""
        manager = RecoveryManager(
            health_check_interval=0.1,
            auto_recovery=True,
        )
        return manager

    @pytest.mark.asyncio
    async def test_check_io_board_health_success(self, manager):
        """Test IO Board health check success."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        manager._io_board_client = mock_client

        result = await manager.check_io_board_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_io_board_health_failure(self, manager):
        """Test IO Board health check failure."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        manager._io_board_client = mock_client

        result = await manager.check_io_board_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_io_board_health_no_client(self, manager):
        """Test IO Board health check with no client."""
        result = await manager.check_io_board_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_camera_health_success(self, manager):
        """Test camera health check success."""
        mock_camera_client = AsyncMock()
        mock_camera_client.check_all_cameras = AsyncMock(return_value={
            "cameras": {
                0: {"connected": True},
                1: {"connected": True},
            }
        })
        manager._camera_client = mock_camera_client

        result = await manager.check_camera_health()
        assert result == {0: True, 1: True}

    @pytest.mark.asyncio
    async def test_check_camera_health_partial(self, manager):
        """Test camera health check with some failures."""
        mock_camera_client = AsyncMock()
        mock_camera_client.check_all_cameras = AsyncMock(return_value={
            "cameras": {
                0: {"connected": True},
                1: {"connected": False},
            }
        })
        manager._camera_client = mock_camera_client

        result = await manager.check_camera_health()
        assert result[0] is True
        assert result[1] is False

    @pytest.mark.asyncio
    async def test_attempt_recovery_with_handler(self, manager):
        """Test recovery attempt with registered handler."""
        handler = AsyncMock(return_value=True)
        manager.register_service("camera", recovery_handler=handler)

        result = await manager._attempt_recovery("camera")

        assert result is True
        handler.assert_called_once()

        status = manager.get_service_status("camera")
        assert status.status == RecoveryStatus.HEALTHY
        assert status.recovery_count == 1

    @pytest.mark.asyncio
    async def test_attempt_recovery_handler_fails(self, manager):
        """Test recovery attempt when handler fails."""
        handler = AsyncMock(return_value=False)
        manager.register_service("camera", recovery_handler=handler)

        result = await manager._attempt_recovery("camera")

        assert result is False

        status = manager.get_service_status("camera")
        assert status.status == RecoveryStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_attempt_recovery_no_handler(self, manager):
        """Test recovery attempt with no handler."""
        manager.register_service("camera")

        result = await manager._attempt_recovery("camera")

        assert result is False

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, manager):
        """Test starting and stopping monitoring."""
        manager.register_service("io_board")

        await manager.start_monitoring()
        assert manager._running is True
        assert manager._monitor_task is not None

        await asyncio.sleep(0.05)  # Let it run briefly

        await manager.stop_monitoring()
        assert manager._running is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
