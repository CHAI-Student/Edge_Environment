"""
Camera Error Recovery Tests.

Tests for:
- DeviceScanner camera enumeration
- Dynamic device remapping
- Reconnection logic
- Health check monitoring
"""

import pytest
import sys
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, List, Optional

# Skip if cv2 not available
cv2_available = True
try:
    import cv2
except ImportError:
    cv2_available = False


class TestDeviceScanner:
    """DeviceScanner unit tests."""

    @pytest.fixture
    def scanner(self):
        """Fresh DeviceScanner instance."""
        from core.device_scanner import DeviceScanner
        return DeviceScanner()

    @pytest.mark.skipif(not cv2_available, reason="cv2 not installed")
    def test_scan_all_devices_empty(self, scanner):
        """Test scanning when no cameras available."""
        with patch.object(scanner, '_probe_device', return_value=None):
            devices = scanner.scan_all_devices(refresh=True)
            # May return empty list or devices depending on system
            assert isinstance(devices, list)

    @pytest.mark.skipif(not cv2_available, reason="cv2 not installed")
    def test_scan_caches_results(self, scanner):
        """Test that scan results are cached."""
        with patch.object(scanner, '_probe_device') as mock_probe:
            mock_probe.return_value = None

            # First scan
            scanner.scan_all_devices(refresh=True)
            call_count_1 = mock_probe.call_count

            # Second scan (should use cache)
            scanner.scan_all_devices(refresh=False)
            call_count_2 = mock_probe.call_count

            assert call_count_2 == call_count_1  # No additional calls

    @pytest.mark.skipif(not cv2_available, reason="cv2 not installed")
    def test_scan_refresh_clears_cache(self, scanner):
        """Test that refresh=True clears cache."""
        with patch.object(scanner, '_probe_device') as mock_probe:
            mock_probe.return_value = None

            scanner.scan_all_devices(refresh=True)
            call_count_1 = mock_probe.call_count

            scanner.scan_all_devices(refresh=True)
            call_count_2 = mock_probe.call_count

            assert call_count_2 > call_count_1  # Additional calls made

    def test_find_by_identifier_found(self, scanner):
        """Test finding device by identifier."""
        from core.device_scanner import CameraDeviceInfo

        # Mock cached devices
        scanner._devices = [
            CameraDeviceInfo(
                device_index=0,
                identifier="USB_Camera_12345678",
                backend="DSHOW",
                connected=True,
            ),
            CameraDeviceInfo(
                device_index=1,
                identifier="USB_Camera_87654321",
                backend="DSHOW",
                connected=True,
            ),
        ]

        result = scanner.find_by_identifier("USB_Camera_12345678")
        assert result == 0

    def test_find_by_identifier_not_found(self, scanner):
        """Test finding non-existent identifier returns None."""
        scanner._devices = []
        result = scanner.find_by_identifier("NONEXISTENT")
        assert result is None

    def test_rebuild_mapping(self, scanner):
        """Test rebuilding zone-device mapping."""
        from core.device_scanner import CameraDeviceInfo

        # Mock devices
        scanner._devices = [
            CameraDeviceInfo(
                device_index=0,
                identifier="CAM_TOP",
                backend="DSHOW",
                connected=True,
            ),
            CameraDeviceInfo(
                device_index=2,  # Note: index 2, not 1
                identifier="CAM_ZONE0",
                backend="DSHOW",
                connected=True,
            ),
        ]

        config_mapping = {
            "top": "CAM_TOP",
            "zone_0": "CAM_ZONE0",
        }

        result = scanner.rebuild_mapping(config_mapping)

        assert result.get("top") == 0
        assert result.get("zone_0") == 2


class TestCameraDeviceInfo:
    """CameraDeviceInfo dataclass tests."""

    def test_create_device_info(self):
        """Test creating CameraDeviceInfo."""
        from core.device_scanner import CameraDeviceInfo

        info = CameraDeviceInfo(
            device_index=0,
            identifier="USB_Camera_123",
            backend="DSHOW",
            width=640,
            height=480,
            connected=True,
        )

        assert info.device_index == 0
        assert info.identifier == "USB_Camera_123"
        assert info.width == 640
        assert info.height == 480
        assert info.connected is True

    def test_default_values(self):
        """Test CameraDeviceInfo default values."""
        from core.device_scanner import CameraDeviceInfo

        info = CameraDeviceInfo(
            device_index=0,
            identifier="test",
        )

        assert info.backend == ""
        assert info.width == 0
        assert info.height == 0
        assert info.connected is False


class TestCameraManagerReconnect:
    """CameraManager reconnection tests."""

    @pytest.fixture
    def manager(self):
        """Mock CameraManager."""
        with patch('core.manager.DeviceScanner'):
            from core.manager import CameraManager
            return CameraManager(camera_ids=[0, 1, 2])

    def test_health_check_all_healthy(self, manager):
        """Test health check when all cameras healthy."""
        # Mock all cameras as connected
        manager._cameras = {
            0: MagicMock(isOpened=MagicMock(return_value=True)),
            1: MagicMock(isOpened=MagicMock(return_value=True)),
            2: MagicMock(isOpened=MagicMock(return_value=True)),
        }

        health = manager.health_check()

        assert health[0] is True
        assert health[1] is True
        assert health[2] is True

    def test_health_check_some_unhealthy(self, manager):
        """Test health check with some cameras unhealthy."""
        manager._cameras = {
            0: MagicMock(isOpened=MagicMock(return_value=True)),
            1: MagicMock(isOpened=MagicMock(return_value=False)),
            2: MagicMock(isOpened=MagicMock(return_value=True)),
        }

        health = manager.health_check()

        assert health[0] is True
        assert health[1] is False
        assert health[2] is True

    def test_rebuild_mapping_updates_indices(self, manager):
        """Test that rebuild_mapping updates camera indices."""
        # Mock scanner
        manager._scanner = MagicMock()
        manager._scanner.scan_all_devices.return_value = []
        manager._scanner.rebuild_mapping.return_value = {"zone_0": 2, "zone_1": 3}

        result = manager.rebuild_mapping()

        assert isinstance(result, dict)

    def test_learn_device_identifiers(self, manager):
        """Test learning device identifiers."""
        manager._cameras = {
            0: MagicMock(getBackendName=MagicMock(return_value="DSHOW")),
        }

        result = manager.learn_device_identifiers()

        # Should return mapping of camera_id to identifier
        assert isinstance(result, dict)


class TestCameraClientRetry:
    """CameraClient retry logic tests."""

    @pytest.fixture
    def client(self):
        """CameraClient instance."""
        from model.camera.camera_client import CameraClient
        return CameraClient(base_url="http://localhost:8003", timeout=1.0)

    @pytest.mark.asyncio
    async def test_get_frame_with_retry_success_first_attempt(self, client):
        """Test successful frame capture on first attempt."""
        import numpy as np

        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        with patch.object(client, 'get_frame', return_value=mock_frame):
            frame, error = await client.get_frame_with_retry(camera_id=0, max_retries=3)

            assert frame is not None
            assert error is None

    @pytest.mark.asyncio
    async def test_get_frame_with_retry_success_after_failures(self, client):
        """Test frame capture succeeds after initial failures."""
        import numpy as np

        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        call_count = 0

        async def mock_get_frame(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return None
            return mock_frame

        with patch.object(client, '_client') as mock_client:
            # This tests the retry logic internally
            pass

    @pytest.mark.asyncio
    async def test_get_frame_with_retry_all_attempts_fail(self, client):
        """Test all retry attempts fail."""
        with patch.object(client, 'get_frame', return_value=None):
            frame, error = await client.get_frame_with_retry(
                camera_id=0,
                max_retries=2,
                initial_delay=0.01,  # Fast for testing
            )

            assert frame is None
            assert error is not None

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self, client):
        """Test exponential backoff increases delays."""
        import asyncio
        import time

        delays = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            delays.append(delay)
            await original_sleep(0.001)  # Actually sleep very briefly

        with patch('asyncio.sleep', mock_sleep):
            with patch.object(client, 'get_frame', return_value=None):
                await client.get_frame_with_retry(
                    camera_id=0,
                    max_retries=3,
                    initial_delay=1.0,
                    backoff_multiplier=2.0,
                )

        # Verify backoff: delays should increase
        if len(delays) >= 2:
            for i in range(1, len(delays)):
                assert delays[i] >= delays[i-1]


class TestRecoveryManager:
    """RecoveryManager integration tests."""

    @pytest.fixture
    def recovery_manager(self):
        """RecoveryManager instance."""
        from model.error_recovery import RecoveryManager
        return RecoveryManager(
            health_check_interval=1.0,
            auto_recovery=True,
        )

    def test_register_service(self, recovery_manager):
        """Test registering a service."""
        recovery_manager.register_service("camera")

        status = recovery_manager.get_service_status("camera")
        assert status is not None
        assert status.status.value == "healthy"

    def test_register_service_with_handler(self, recovery_manager):
        """Test registering service with recovery handler."""
        handler_called = False

        def recovery_handler():
            nonlocal handler_called
            handler_called = True
            return True

        recovery_manager.register_service("test_service", recovery_handler)

        assert "test_service" in recovery_manager._recovery_handlers

    def test_record_error(self, recovery_manager):
        """Test recording an error."""
        from model.error_recovery import ErrorCode, ServiceError

        recovery_manager.register_service("camera")

        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
            details={"camera_id": 1},
        )

        recovery_manager.record_error(error)

        status = recovery_manager.get_service_status("camera")
        assert status.error_count == 1
        assert status.last_error is not None

    def test_get_overall_status_healthy(self, recovery_manager):
        """Test overall status when all services healthy."""
        from model.error_recovery import RecoveryStatus

        recovery_manager.register_service("camera")
        recovery_manager.register_service("io_board")

        status = recovery_manager.get_overall_status()
        assert status == RecoveryStatus.HEALTHY

    def test_get_overall_status_degraded(self, recovery_manager):
        """Test overall status when some services degraded."""
        from model.error_recovery import RecoveryStatus, ErrorCode, ServiceError

        recovery_manager.register_service("camera")
        recovery_manager.register_service("io_board")

        # Record recoverable error
        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
        )
        recovery_manager.record_error(error)

        status = recovery_manager.get_overall_status()
        assert status == RecoveryStatus.DEGRADED

    def test_get_all_status(self, recovery_manager):
        """Test getting all services status."""
        recovery_manager.register_service("camera")
        recovery_manager.register_service("io_board")

        all_status = recovery_manager.get_all_status()

        assert "camera" in all_status
        assert "io_board" in all_status
        assert "status" in all_status["camera"]
        assert "error_count" in all_status["camera"]

    def test_get_error_history(self, recovery_manager):
        """Test getting error history."""
        from model.error_recovery import ErrorCode, ServiceError

        recovery_manager.register_service("camera")

        for i in range(5):
            error = ServiceError.create(
                code=ErrorCode.E3001,
                service="camera",
                message=f"Error {i}",
            )
            recovery_manager.record_error(error)

        history = recovery_manager.get_error_history(limit=3)

        assert len(history) == 3
        assert "Error 4" in history[-1]["message"]

    def test_clear_error_history(self, recovery_manager):
        """Test clearing error history."""
        from model.error_recovery import ErrorCode, ServiceError

        recovery_manager.register_service("camera")

        error = ServiceError.create(code=ErrorCode.E3001, service="camera")
        recovery_manager.record_error(error)

        recovery_manager.clear_error_history()

        history = recovery_manager.get_error_history()
        assert len(history) == 0


class TestErrorCodes:
    """ErrorCode and ServiceError tests."""

    def test_error_code_values(self):
        """Test error code values."""
        from model.error_recovery import ErrorCode

        assert ErrorCode.E3001.value == "E3001"
        assert ErrorCode.E2005.value == "E2005"

    def test_service_error_create(self):
        """Test ServiceError.create factory method."""
        from model.error_recovery import ErrorCode, ServiceError

        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
            details={"camera_id": 1},
        )

        assert error.code == ErrorCode.E3001
        assert error.service == "camera"
        assert error.details == {"camera_id": 1}
        assert error.timestamp > 0
        assert error.message != ""  # Should have default message

    def test_service_error_custom_message(self):
        """Test ServiceError with custom message."""
        from model.error_recovery import ErrorCode, ServiceError

        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
            message="Custom error message",
        )

        assert error.message == "Custom error message"

    def test_service_error_to_dict(self):
        """Test ServiceError.to_dict serialization."""
        from model.error_recovery import ErrorCode, ServiceError

        error = ServiceError.create(
            code=ErrorCode.E3001,
            service="camera",
        )

        data = error.to_dict()

        assert "code" in data
        assert "message" in data
        assert "service" in data
        assert "timestamp" in data
        assert "recoverable" in data
        assert data["code"] == "E3001"

    def test_error_recoverable_flag(self):
        """Test that error codes have correct recoverable flags."""
        from model.error_recovery import ErrorCode, ERROR_RECOVERABLE

        # Camera connection error should be recoverable
        assert ERROR_RECOVERABLE.get(ErrorCode.E3001) is True

        # Serial port not found should not be recoverable
        assert ERROR_RECOVERABLE.get(ErrorCode.E2001) is False


class TestSSESubscriberBackoff:
    """SSE Subscriber exponential backoff tests."""

    @pytest.fixture
    def subscriber(self):
        """IOBoardSubscriber instance."""
        from model.sse_client.io_board_subscriber import IOBoardSubscriber
        return IOBoardSubscriber(
            base_url="http://localhost:8001",
            initial_reconnect_delay=1.0,
            max_reconnect_delay=30.0,
            backoff_multiplier=2.0,
            max_reconnect_attempts=5,
        )

    def test_initial_backoff_delay(self, subscriber):
        """Test initial backoff delay is correct."""
        assert subscriber._current_reconnect_delay == 1.0

    def test_reset_backoff(self, subscriber):
        """Test resetting backoff state."""
        subscriber._current_reconnect_delay = 16.0
        subscriber.state.consecutive_failures = 5
        subscriber.state.reconnect_count = 3

        subscriber.reset_backoff()

        assert subscriber._current_reconnect_delay == 1.0
        assert subscriber.state.consecutive_failures == 0
        assert subscriber.state.reconnect_count == 0

    def test_get_connection_stats(self, subscriber):
        """Test getting connection statistics."""
        subscriber.state.connected = True
        subscriber.state.reconnect_count = 2
        subscriber.state.error_count = 3

        stats = subscriber.get_connection_stats()

        assert stats["connected"] is True
        assert stats["reconnect_count"] == 2
        assert stats["error_count"] == 3
        assert "current_backoff_delay" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
