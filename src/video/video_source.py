"""
src/video/video_source.py
==========================
PURPOSE:
    Handles opening and reading from any video source:
    - MP4 / AVI / MKV video files
    - Webcam (built-in or USB)
    - RTSP CCTV streams

CONCEPTS FOR BEGINNERS:
    - Frame: A single image from a video. A 30fps video has 30 frames per second.
    - OpenCV VideoCapture: OpenCV's built-in tool for reading video frames.
    - RTSP: Real-Time Streaming Protocol — how IP cameras stream video over a network.

HOW TO USE:
    from src.video.video_source import VideoSource

    source = VideoSource("data/test_videos/test.mp4", camera_id="cam_01")
    source.open()

    while True:
        ok, frame = source.read()
        if not ok:
            break
        # process frame...

    source.release()
"""


import sys
from pathlib import Path
from typing import Optional, Tuple
import cv2
import numpy as np


from src.utils.logger import get_logger
from src.utils.time_utils import now_ts

logger = get_logger(__name__)


class VideoSource:
    """
    Unified video source for files, webcams and RTSP streams.

    Attributes:
        source:         Path/URL/integer for the video source
        camera_id:      Identifier string for this camera
        cap:            OpenCV VideoCapture object (opened after .open())
        frame_count:    Total frames read so far
        fps:            Detected frames-per-second of the source
        width:          Frame width in pixels
        height:         Frame height in pixels
        is_file:        True if source is a local video file
        is_rtsp:        True if source is an RTSP stream
        is_webcam:      True if source is a webcam (integer)
    """

    def __init__(self, source, camera_id: str = "camera_001"):
        """
        Initialize the video source (does NOT open it yet).

        Args:
            source:    One of:
                       - String path to video file: "data/test_videos/test.mp4"
                       - Integer for webcam: 0 (first webcam), 1 (second), etc.
                       - RTSP URL: "rtsp://user:pass@192.168.1.100:554/stream"
            camera_id: Identifier for this camera used in events/logs
        """
        self.source = source
        self.camera_id = camera_id
        self.cap: Optional[cv2.VideoCapture] = None

        # These are populated after open()
        self.frame_count: int = 0
        self.fps: float = 30.0
        self.width: int = 0
        self.height: int = 0
        self._open_time: float = 0.0
        self._last_frame_time: float = 0.0
        self._connected: bool = False

        # Detect source type
        self.is_webcam = isinstance(source, int)
        self.is_rtsp = isinstance(source, str) and source.lower().startswith("rtsp://")
        self.is_file = isinstance(source, str) and not self.is_rtsp

        logger.info(
            f"VideoSource created | camera={camera_id} | "
            f"source={source} | type={'webcam' if self.is_webcam else 'rtsp' if self.is_rtsp else 'file'}"
        )

    def open(self) -> bool:
        """
        Open the video source and read its properties.

        Returns:
            True if opened successfully, False otherwise.
        """
        try:
            # Validate file existence before attempting to open
            if self.is_file:
                p = Path(str(self.source))
                if not p.exists():
                    logger.error(
                        f"Video file not found: {self.source}\n"
                        f"  Please place your video at: {p.absolute()}\n"
                        f"  Or update config/cameras.yaml with the correct path."
                    )
                    return False

            logger.info(f"Opening video source: {self.source}")

            # On Windows, try DirectShow backend for webcams — more reliable than MSMF
            if self.is_webcam and sys.platform == "win32":
                logger.info("Windows webcam: trying DirectShow backend (CAP_DSHOW)...")
                self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    logger.warning("DirectShow failed — retrying with default backend...")
                    self.cap = cv2.VideoCapture(self.source)
            else:
                self.cap = cv2.VideoCapture(self.source)

            if not self.cap.isOpened():
                logger.error(f"Failed to open video source: {self.source}")
                if self.is_webcam:
                    logger.error(
                        "  Webcam fix options:\n"
                        "  1. Close Teams, Zoom, OBS or any app using the webcam\n"
                        "  2. Check Windows Settings → Privacy → Camera → Allow apps\n"
                        "  3. Try a video file: python src/main.py --source path/to/video.mp4"
                    )
                elif self.is_rtsp:
                    logger.error(
                        "  RTSP fix: Check camera IP, credentials, and network connection."
                    )
                return False


            # Read video properties
            self.fps    = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.width  = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

            self._open_time = now_ts()
            self._connected = True

            logger.info(
                f"Video opened: {self.width}x{self.height} @ {self.fps:.1f}fps"
                + (f" | {total_frames} frames total" if total_frames > 0 else "")
            )
            return True

        except Exception as e:
            logger.error(f"Exception opening video source '{self.source}': {e}")
            return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read the next frame from the video source.

        Returns:
            Tuple of (success: bool, frame: numpy array or None)

        Example:
            ok, frame = source.read()
            if ok:
                cv2.imshow("frame", frame)
            else:
                print("Video ended or camera disconnected")
        """
        if self.cap is None or not self.cap.isOpened():
            return False, None

        try:
            ret, frame = self.cap.read()
            if ret:
                self.frame_count += 1
                self._last_frame_time = now_ts()
                return True, frame
            else:
                if self.is_file:
                    logger.info(f"Video file ended after {self.frame_count} frames.")
                else:
                    logger.warning(
                        f"Frame read failed on camera '{self.camera_id}' "
                        f"after {self.frame_count} frames."
                    )
                self._connected = False
                return False, None

        except Exception as e:
            logger.error(f"Frame read error on camera '{self.camera_id}': {e}")
            self._connected = False
            return False, None

    def rewind(self) -> bool:
        """
        Rewind video file to the beginning (for looping test videos).
        Does nothing for webcams or RTSP streams.

        Returns:
            True if rewound successfully.
        """
        if self.is_file and self.cap is not None:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.frame_count = 0
            self._connected = True
            logger.info(f"Video rewound to start: {self.source}")
            return True
        return False

    def release(self) -> None:
        """Release the video source and free resources."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            self._connected = False
            logger.info(
                f"VideoSource released | camera={self.camera_id} | "
                f"frames_read={self.frame_count}"
            )

    @property
    def is_connected(self) -> bool:
        """True if the source is currently open and providing frames."""
        return self._connected and self.cap is not None and self.cap.isOpened()

    @property
    def uptime_seconds(self) -> float:
        """How long this source has been open (in seconds)."""
        if self._open_time == 0:
            return 0.0
        return now_ts() - self._open_time

    def get_info(self) -> dict:
        """Return a dictionary of source properties."""
        return {
            "camera_id":  self.camera_id,
            "source":     str(self.source),
            "type":       "webcam" if self.is_webcam else "rtsp" if self.is_rtsp else "file",
            "width":      self.width,
            "height":     self.height,
            "fps":        self.fps,
            "frame_count": self.frame_count,
            "is_connected": self.is_connected,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }

    def __repr__(self) -> str:
        return f"VideoSource(camera_id={self.camera_id!r}, source={self.source!r})"
