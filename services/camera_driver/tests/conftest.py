"""
Pytest Fixtures for Camera Driver Tests.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add parent directories to path for imports
services_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(services_dir))
sys.path.insert(0, str(services_dir / "camera_driver"))
sys.path.insert(0, str(services_dir / "model"))


@pytest.fixture
def mock_cv2_video_capture():
    """Mock cv2.VideoCapture."""
    mock = MagicMock()
    mock.isOpened.return_value = True
    mock.read.return_value = (True, MagicMock())
    mock.get.return_value = 640
    mock.getBackendName.return_value = "DSHOW"
    return mock


@pytest.fixture
def sample_camera_ids():
    """Sample camera IDs for testing."""
    return [0, 1, 2, 3, 4, 5]


@pytest.fixture
def sample_zone_camera_map():
    """Zone to camera mapping."""
    return {
        "top": 0,
        "zone_0": 1,
        "zone_1": 2,
        "zone_2": 3,
        "zone_3": 4,
        "zone_4": 5,
    }


@pytest.fixture
def sample_camera_id_mapping():
    """Camera identifier mapping."""
    return {
        "USB_Camera_TOP": {"zone": "top", "camera_id": 0},
        "USB_Camera_Z0": {"zone": 0, "camera_id": 1},
        "USB_Camera_Z1": {"zone": 1, "camera_id": 2},
        "USB_Camera_Z2": {"zone": 2, "camera_id": 3},
        "USB_Camera_Z3": {"zone": 3, "camera_id": 4},
        "USB_Camera_Z4": {"zone": 4, "camera_id": 5},
    }
