"""
Pytest Fixtures for Model Service Tests.
"""

import pytest
import sys
import tempfile
import numpy as np
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path for imports
model_dir = Path(__file__).parent.parent
sys.path.insert(0, str(model_dir))


# Test data fixtures


@pytest.fixture
def sample_loadcell_values() -> List[float]:
    """샘플 로드셀 값 (10채널)."""
    return [432.0, 433.0, 260.0, 260.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


@pytest.fixture
def sample_loadcell_change_event() -> Dict[str, Any]:
    """샘플 loadcell.change 이벤트."""
    return {
        "event": "loadcell.change",
        "changed_indices": [0, 1],
        "old_values": [800.0, 800.0, 260.0, 260.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "new_values": [435.0, 430.0, 260.0, 260.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "deltas": [-365.0, -370.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "timestamp": 1737446400.123,
    }


@pytest.fixture
def sample_frame() -> np.ndarray:
    """샘플 프레임 (640x480 RGB)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def sample_product_list() -> List[Dict[str, Any]]:
    """샘플 상품 목록."""
    return [
        {"id": 1, "name": "chickenmayo_rice", "weight": 365, "price": 3500},
        {"id": 2, "name": "hotbar", "weight": 120, "price": 1500},
        {"id": 3, "name": "samdasoo_500", "weight": 520, "price": 1000},
        {"id": 4, "name": "pocari_500", "weight": 530, "price": 1500},
        {"id": 5, "name": "pepero", "weight": 69, "price": 1500},
    ]


@pytest.fixture
def sample_vision_candidates() -> List[Dict[str, Any]]:
    """샘플 Vision 후보군."""
    return [
        {"class_id": 1, "name": "chickenmayo_rice", "confidence": 0.85},
        {"class_id": 2, "name": "hotbar", "confidence": 0.72},
        {"class_id": 3, "name": "samdasoo_500", "confidence": 0.65},
    ]


@pytest.fixture
def sample_ensemble_result() -> List[Dict[str, Any]]:
    """샘플 앙상블 결과."""
    return [
        {
            "class_id": 1,
            "name": "chickenmayo_rice",
            "combined_confidence": 0.905,
            "source": "consensus",
        },
        {
            "class_id": 2,
            "name": "hotbar",
            "combined_confidence": 0.68,
            "source": "top_only",
        },
    ]


# Mock fixtures


@pytest.fixture
def mock_camera_client(mocker):
    """Mock CameraClient."""
    mock = mocker.patch("camera.camera_client.CameraClient")
    instance = mock.return_value
    instance.get_frame.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    instance.activate_zone.return_value = True
    instance.deactivate_zone.return_value = True
    return instance


@pytest.fixture
def mock_yolo_wrapper(mocker, sample_vision_candidates):
    """Mock YOLOWrapper."""
    mock = mocker.patch("vision.yolo_wrapper.YOLOWrapper")
    instance = mock.return_value
    instance.detect.return_value = sample_vision_candidates
    return instance


# Helper fixtures


@pytest.fixture
def zone_channel_map() -> Dict[int, List[int]]:
    """Zone-Channel 매핑."""
    return {
        0: [0, 1],
        1: [2, 3],
        2: [4, 5],
        3: [6, 7],
        4: [8, 9],
    }


@pytest.fixture
def zone_camera_map() -> Dict[int, int]:
    """Zone-Camera 매핑."""
    return {
        0: 1,
        1: 2,
        2: 3,
        3: 4,
        4: 5,
    }


# Product Registration fixtures


@pytest.fixture
def sample_product_data() -> Dict[str, Any]:
    """샘플 상품 등록 데이터."""
    return {
        "name": "새우깡",
        "category": "snack",
        "weight": 90.0,
        "price": 1500,
        "barcode": "8801234567890",
    }


@pytest.fixture
def temp_product_file():
    """임시 상품 파일 경로."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        yield f.name
    # Cleanup
    import os
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def temp_image_dir():
    """임시 이미지 디렉토리."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# Error Recovery fixtures


@pytest.fixture
def sample_error_codes() -> List[str]:
    """샘플 에러 코드 목록."""
    return [
        "E2001",  # Serial port not found
        "E2005",  # Timeout
        "E3001",  # Camera connection failed
        "E3002",  # Frame capture failed
        "E4001",  # Model load failed
        "E5001",  # SSE connection failed
    ]


@pytest.fixture
def mock_recovery_handler():
    """Mock 복구 핸들러."""
    from unittest.mock import MagicMock
    handler = MagicMock(return_value=True)
    return handler


@pytest.fixture
def mock_async_recovery_handler():
    """Mock 비동기 복구 핸들러."""
    from unittest.mock import AsyncMock
    handler = AsyncMock(return_value=True)
    return handler
