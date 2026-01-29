"""
Camera Module Tests.

FrameCapturer 및 FolderFrameLoader 테스트.
"""

import pytest
import os
import tempfile
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camera.frame_capturer import CapturedFrames, FolderFrameLoader
from config import get_snapshot_folder, get_top_camera_path, get_side_camera_path, generate_session_id


class TestCapturedFrames:
    """CapturedFrames 데이터클래스 테스트."""

    def test_has_both_true(self):
        """양쪽 프레임이 모두 있는 경우."""
        frames = CapturedFrames(
            zone_id=0,
            top_frame=np.zeros((480, 640, 3), dtype=np.uint8),
            side_frame=np.zeros((480, 640, 3), dtype=np.uint8),
            top_camera_id=0,
            side_camera_id=1,
            timestamp=1234567890.0,
        )

        assert frames.has_both == True
        assert frames.has_any == True

    def test_has_both_false(self):
        """한쪽 프레임만 있는 경우."""
        frames = CapturedFrames(
            zone_id=0,
            top_frame=np.zeros((480, 640, 3), dtype=np.uint8),
            side_frame=None,
            top_camera_id=0,
            side_camera_id=1,
            timestamp=1234567890.0,
        )

        assert frames.has_both == False
        assert frames.has_any == True

    def test_has_any_false(self):
        """프레임이 없는 경우."""
        frames = CapturedFrames(
            zone_id=0,
            top_frame=None,
            side_frame=None,
            top_camera_id=0,
            side_camera_id=1,
            timestamp=1234567890.0,
        )

        assert frames.has_both == False
        assert frames.has_any == False


class TestConfigPaths:
    """Config 경로 함수 테스트."""

    def test_get_snapshot_folder(self):
        """스냅샷 폴더 경로."""
        session_id = "260121_143025"
        folder = get_snapshot_folder(session_id)

        assert session_id in folder
        assert folder.endswith(session_id) or folder.endswith(session_id + os.sep)

    def test_get_top_camera_path(self):
        """Top 카메라 이미지 경로."""
        session_id = "260121_143025"
        path = get_top_camera_path(session_id)

        assert session_id in path
        assert path.endswith(".jpg")
        assert "top" in path.lower()

    def test_get_side_camera_path(self):
        """Side 카메라 이미지 경로."""
        session_id = "260121_143025"

        for zone_id in range(5):
            path = get_side_camera_path(session_id, zone_id)

            assert session_id in path
            assert path.endswith(".jpg")
            assert str(zone_id) in path

    def test_generate_session_id(self):
        """세션 ID 생성."""
        session_id = generate_session_id()

        # 형식: YYMMDD_HHMMSS
        assert len(session_id) == 13  # 6 + 1 + 6
        assert "_" in session_id


class TestFolderFrameLoader:
    """FolderFrameLoader 테스트."""

    @pytest.fixture
    def temp_snapshot_folder(self):
        """임시 스냅샷 폴더."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_load_zone_nonexistent_folder(self):
        """존재하지 않는 폴더에서 로드."""
        loader = FolderFrameLoader()

        frames = loader.load_zone(
            session_id="nonexistent_session_id",
            zone_id=0
        )

        assert frames.top_frame is None
        assert frames.side_frame is None
        assert frames.has_any == False

    def test_check_folder_exists_false(self):
        """폴더 존재 확인 (없음)."""
        loader = FolderFrameLoader()

        exists = loader.check_folder_exists("nonexistent_session")

        assert exists == False

    def test_list_available_images_empty(self):
        """빈 폴더의 이미지 목록."""
        loader = FolderFrameLoader()

        available = loader.list_available_images("nonexistent_session")

        assert available["top"] == False
        for zone_id in range(5):
            assert available["zones"][zone_id] == False

    def test_load_top_only(self):
        """Top 이미지만 로드."""
        loader = FolderFrameLoader()

        frame = loader.load_top_only("nonexistent_session")

        assert frame is None

    def test_load_side_only(self):
        """Side 이미지만 로드."""
        loader = FolderFrameLoader()

        frame = loader.load_side_only("nonexistent_session", zone_id=0)

        assert frame is None

    def test_load_all_zones(self):
        """모든 Zone 로드."""
        loader = FolderFrameLoader()

        all_frames = loader.load_all_zones("nonexistent_session")

        assert len(all_frames) == 5
        for frames in all_frames:
            assert frames.top_frame is None
            assert frames.side_frame is None


class TestZoneCameraMapping:
    """Zone-Camera 매핑 테스트."""

    def test_zone_camera_consistency(self):
        """Zone-Camera 매핑 일관성."""
        from config import get_zone_cameras, ZONE_CAMERA_MAP, TOP_CAMERA_ID

        for zone_id in range(5):
            top_id, side_id = get_zone_cameras(zone_id)

            assert top_id == TOP_CAMERA_ID  # Top은 항상 0
            assert side_id == ZONE_CAMERA_MAP.get(zone_id)

    def test_all_zones_have_cameras(self):
        """모든 Zone에 카메라 매핑."""
        from config import ZONE_CAMERA_MAP

        for zone_id in range(5):
            assert zone_id in ZONE_CAMERA_MAP
            assert ZONE_CAMERA_MAP[zone_id] > 0  # Side 카메라는 1~5


class TestFrameCapturerModes:
    """FrameCapturer 모드 테스트."""

    def test_api_mode_requires_client(self):
        """API 모드는 CameraClient 필요."""
        from camera.frame_capturer import FrameCapturer

        # CameraClient 없이 생성
        capturer = FrameCapturer(camera_client=None, auto_activate=False)

        # _owns_client가 True여야 함
        assert capturer._owns_client == True

    def test_folder_mode_independent(self):
        """폴더 모드는 독립적."""
        loader = FolderFrameLoader()

        # CameraClient 없이도 동작
        frames = loader.load_zone("test_session", 0)

        # None이지만 에러 없이 동작
        assert isinstance(frames, CapturedFrames)
