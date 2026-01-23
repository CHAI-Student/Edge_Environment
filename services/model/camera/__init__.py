"""
Camera Client module for camera_driver integration.

camera_driver 서비스와 HTTP 통신하여 프레임을 캡처합니다.

두 가지 모드 지원:
1. API 모드 (FrameCapturer): camera_driver HTTP API를 통해 실시간 캡처
2. 폴더 모드 (FolderFrameLoader): 미리 합의된 경로에서 저장된 이미지를 직접 로드
"""

from .camera_client import CameraClient
from .frame_capturer import FrameCapturer, CapturedFrames, FolderFrameLoader

__all__ = [
    "CameraClient",
    "FrameCapturer",
    "FolderFrameLoader",
    "CapturedFrames",
]
