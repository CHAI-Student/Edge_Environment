"""
Streaming Frame Extractor using FFmpeg.

Memory-efficient frame extraction from video files using ffmpeg subprocess.
Supports hardware-accelerated decoding (NVDEC) on Jetson.

Usage:
    extractor = StreamingFrameExtractor("video.avi")
    for frame in extractor:
        # Process frame (numpy array BGR)
        pass
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Iterator, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class StreamingFrameExtractor:
    """
    Memory-efficient streaming frame extractor using FFmpeg.

    Uses ffmpeg subprocess with pipe output for minimal memory footprint.
    Supports NVDEC hardware acceleration on Jetson Orin Nano.

    Attributes:
        video_path: Path to the video file
        total_frames: Total number of frames in the video
        fps: Frames per second
        width: Frame width
        height: Frame height
    """

    def __init__(
        self,
        video_path: str,
        use_hwaccel: bool = True,
        pixel_format: str = "bgr24",
    ):
        """
        Initialize frame extractor.

        Args:
            video_path: Path to the video file (AVI, MP4, etc.)
            use_hwaccel: Use hardware acceleration (NVDEC) if available
            pixel_format: Output pixel format (bgr24 for OpenCV compatibility)
        """
        self.video_path = str(video_path)
        self.use_hwaccel = use_hwaccel
        self.pixel_format = pixel_format

        self._width: int = 0
        self._height: int = 0
        self._fps: float = 0.0
        self._total_frames: int = 0
        self._duration: float = 0.0
        self._initialized = False
        self._hwaccel_available: Optional[bool] = None

    def _probe_video(self) -> bool:
        """
        Probe video metadata using ffprobe.

        Returns:
            True if successful, False otherwise
        """
        if self._initialized:
            return True

        video_file = Path(self.video_path)
        if not video_file.exists():
            logger.error(f"Video file not found: {self.video_path}")
            return False

        # 파일 크기 로깅
        file_size = video_file.stat().st_size
        logger.info(f"[FFPROBE] path={self.video_path}, size={file_size} bytes")

        try:
            cmd = [
                "ffprobe",
                "-v", "error",  # 에러 메시지만 stderr로 출력
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-select_streams", "v:0",
                self.video_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.error(
                    f"ffprobe failed: returncode={result.returncode}, "
                    f"stderr={result.stderr!r}, stdout={result.stdout!r}"
                )
                return False

            info = json.loads(result.stdout)

            # Extract video stream info
            if "streams" not in info or len(info["streams"]) == 0:
                logger.error("No video stream found")
                return False

            stream = info["streams"][0]
            self._width = int(stream.get("width", 0))
            self._height = int(stream.get("height", 0))

            # FPS parsing (can be "30/1" or "29.97")
            fps_str = stream.get("r_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                self._fps = float(num) / float(den) if float(den) > 0 else 0.0
            else:
                self._fps = float(fps_str)

            # Total frames
            self._total_frames = int(stream.get("nb_frames", 0))

            # Duration from format
            if "format" in info:
                self._duration = float(info["format"].get("duration", 0))

            # If nb_frames is missing, estimate from duration
            if self._total_frames == 0 and self._duration > 0 and self._fps > 0:
                self._total_frames = int(self._duration * self._fps)

            self._initialized = True

            logger.debug(
                f"Video probed: {self.video_path}, "
                f"{self._width}x{self._height}, "
                f"{self._fps:.2f}fps, "
                f"{self._total_frames} frames, "
                f"{self._duration:.2f}s"
            )
            return True

        except subprocess.TimeoutExpired:
            logger.error("ffprobe timeout")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"ffprobe JSON parse error: {e}")
            return False
        except Exception as e:
            logger.error(f"ffprobe failed: {e}")
            return False

    def _check_hwaccel(self) -> bool:
        """
        Check if NVDEC hardware acceleration is available.

        Returns:
            True if NVDEC is available
        """
        if self._hwaccel_available is not None:
            return self._hwaccel_available

        try:
            cmd = ["ffmpeg", "-hwaccels"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._hwaccel_available = "cuda" in result.stdout.lower()

            if self._hwaccel_available:
                logger.info("NVDEC hardware acceleration available")
            else:
                logger.debug("NVDEC not available, using CPU decoding")

            return self._hwaccel_available

        except Exception as e:
            logger.debug(f"hwaccel check failed: {e}")
            self._hwaccel_available = False
            return False

    @property
    def total_frames(self) -> int:
        """Total number of frames in the video."""
        if not self._initialized:
            self._probe_video()
        return self._total_frames

    @property
    def fps(self) -> float:
        """Frames per second."""
        if not self._initialized:
            self._probe_video()
        return self._fps

    @property
    def width(self) -> int:
        """Frame width."""
        if not self._initialized:
            self._probe_video()
        return self._width

    @property
    def height(self) -> int:
        """Frame height."""
        if not self._initialized:
            self._probe_video()
        return self._height

    @property
    def duration_seconds(self) -> float:
        """Video duration in seconds."""
        if not self._initialized:
            self._probe_video()
        return self._duration

    @property
    def frame_size(self) -> int:
        """Size of one frame in bytes (BGR24)."""
        return self._width * self._height * 3

    def _build_ffmpeg_cmd(self) -> list:
        """
        Build ffmpeg command for frame extraction.

        Jetson Orin Nano 최적화:
        - MJPEG 코덱 명시 (-c:v mjpeg)
        - NVDEC 하드웨어 가속 (가능한 경우)
        """
        cmd = ["ffmpeg"]

        # Hardware acceleration (Jetson NVDEC)
        if self.use_hwaccel and self._check_hwaccel():
            cmd.extend(["-hwaccel", "cuda"])

        # MJPEG 코덱 명시 (AVI 파일용)
        cmd.extend(["-c:v", "mjpeg"])

        # Input
        cmd.extend(["-i", self.video_path])

        # Output format: raw video to pipe
        cmd.extend([
            "-f", "rawvideo",
            "-pix_fmt", self.pixel_format,
            "-an",  # No audio
            "-sn",  # No subtitles
            "-v", "error",  # Only show errors
            "pipe:1",  # Output to stdout
        ])

        return cmd

    def __iter__(self) -> Iterator[np.ndarray]:
        """
        Iterate over frames.

        Yields:
            Frame as numpy array (BGR format, H x W x 3)
        """
        if not self._probe_video():
            return

        cmd = self._build_ffmpeg_cmd()
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")

        process = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=self.frame_size,
            )

            frame_count = 0
            while True:
                # Read exactly one frame
                raw_frame = process.stdout.read(self.frame_size)

                if len(raw_frame) < self.frame_size:
                    # End of stream or error
                    break

                # Convert to numpy array
                frame = np.frombuffer(raw_frame, dtype=np.uint8)
                frame = frame.reshape((self._height, self._width, 3))

                frame_count += 1
                yield frame

            logger.debug(f"Extracted {frame_count} frames from {self.video_path}")

        except Exception as e:
            logger.error(f"Frame extraction failed: {e}")

        finally:
            if process is not None:
                process.stdout.close()
                process.stderr.close()
                process.terminate()
                process.wait(timeout=5)

    def read_frame(self, frame_number: int) -> Optional[np.ndarray]:
        """
        Read a specific frame by number.

        Uses ffmpeg seek for efficient random access.

        Args:
            frame_number: Frame number (0-indexed)

        Returns:
            Frame as numpy array (BGR) or None if failed
        """
        if not self._probe_video():
            return None

        if frame_number < 0 or frame_number >= self._total_frames:
            logger.warning(
                f"Frame number out of range: {frame_number} "
                f"(total: {self._total_frames})"
            )
            return None

        # Calculate timestamp for seeking
        timestamp = frame_number / self._fps if self._fps > 0 else 0

        cmd = ["ffmpeg"]

        # Hardware acceleration
        if self.use_hwaccel and self._check_hwaccel():
            cmd.extend(["-hwaccel", "cuda"])

        # Seek before input (fast seek)
        cmd.extend(["-ss", f"{timestamp:.6f}"])

        # Input
        cmd.extend(["-i", self.video_path])

        # Output: single frame
        cmd.extend([
            "-frames:v", "1",
            "-f", "rawvideo",
            "-pix_fmt", self.pixel_format,
            "-v", "error",
            "pipe:1",
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,
            )

            if len(result.stdout) < self.frame_size:
                logger.warning(f"Failed to read frame {frame_number}")
                return None

            frame = np.frombuffer(result.stdout[:self.frame_size], dtype=np.uint8)
            frame = frame.reshape((self._height, self._width, 3))
            return frame

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout reading frame {frame_number}")
            return None
        except Exception as e:
            logger.error(f"Failed to read frame {frame_number}: {e}")
            return None

    def __enter__(self) -> "StreamingFrameExtractor":
        """Context manager entry."""
        self._probe_video()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        pass  # No persistent resources to clean up


class CV2FrameExtractor:
    """
    Fallback frame extractor using OpenCV.

    Used when ffmpeg is not available.
    """

    def __init__(self, video_path: str):
        """Initialize with video path."""
        import cv2
        self.video_path = str(video_path)
        self._cap: Optional[cv2.VideoCapture] = None
        self._initialized = False

    def _init_capture(self) -> bool:
        """Initialize video capture."""
        import cv2

        if self._initialized:
            return True

        if not Path(self.video_path).exists():
            logger.error(f"Video file not found: {self.video_path}")
            return False

        self._cap = cv2.VideoCapture(self.video_path)
        if not self._cap.isOpened():
            logger.error(f"Failed to open video: {self.video_path}")
            return False

        self._initialized = True
        return True

    @property
    def total_frames(self) -> int:
        import cv2
        if not self._initialized:
            self._init_capture()
        return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)) if self._cap else 0

    @property
    def fps(self) -> float:
        import cv2
        if not self._initialized:
            self._init_capture()
        return self._cap.get(cv2.CAP_PROP_FPS) if self._cap else 0.0

    @property
    def width(self) -> int:
        import cv2
        if not self._initialized:
            self._init_capture()
        return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self._cap else 0

    @property
    def height(self) -> int:
        import cv2
        if not self._initialized:
            self._init_capture()
        return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self._cap else 0

    def __iter__(self) -> Iterator[np.ndarray]:
        """Iterate over frames."""
        if not self._init_capture():
            return

        while self._cap is not None and self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                break
            yield frame

        self.release()

    def release(self) -> None:
        """Release video capture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __del__(self):
        self.release()


def create_frame_extractor(
    video_path: str,
    prefer_ffmpeg: bool = True,
    use_hwaccel: bool = True,
) -> "StreamingFrameExtractor | CV2FrameExtractor":
    """
    Factory function to create appropriate frame extractor.

    Args:
        video_path: Path to video file
        prefer_ffmpeg: Prefer ffmpeg over cv2 (default: True)
        use_hwaccel: Use hardware acceleration if available

    Returns:
        StreamingFrameExtractor (ffmpeg) or CV2FrameExtractor (fallback)
    """
    if prefer_ffmpeg:
        # Check if ffmpeg is available
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return StreamingFrameExtractor(
                    video_path,
                    use_hwaccel=use_hwaccel,
                )
        except Exception:
            pass

        logger.warning("ffmpeg not available, falling back to cv2")

    return CV2FrameExtractor(video_path)
