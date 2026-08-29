"""
src/detection/detector.py
==========================
PURPOSE:
    Wraps the Ultralytics YOLO model into our own clean Detector class.

    Think of this as the "AI brain" of the system.
    You give it a frame (image), it returns a list of DetectionResult objects.

CONCEPTS FOR BEGINNERS:
    - YOLO Model: A neural network file (.pt) that has learned to recognize
      objects by looking at millions of training images.
    - Inference: The process of running an image through the model to get predictions.
    - Confidence Threshold: We ignore any detection below this score.
      e.g. 0.45 means "only tell me detections you are 45%+ sure about."
    - NMS (Non-Maximum Suppression): Removes duplicate boxes for the same object.
      YOLO handles this internally.

HOW TO USE:
    from src.detection.detector import Detector

    detector = Detector(config)
    detections = detector.detect(frame, frame_number=100)
    for det in detections:
        print(det.class_name, det.confidence, det.bbox)
"""

import time
from pathlib import Path
from typing import List, Optional
import numpy as np

from src.detection.detection_result import (
    DetectionResult,
    ALL_TARGET_CLASSES,
    make_detection,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Detector:
    """
    YOLO-based object detector.

    Loads a pretrained YOLOv8 model and runs inference on video frames.
    Filters results to only return classes we care about (people, vehicles, animals).

    Attributes:
        model_path:   Path to the .pt model weights file
        confidence:   Minimum confidence to accept a detection
        device:       "cpu", "cuda", or "auto"
        target_ids:   List of COCO class IDs to detect
        model:        The loaded YOLO model (set after load())
    """

    def __init__(self, config: dict):
        """
        Initialize the detector from configuration dictionary.

        Args:
            config: The 'model' section from config.yaml

        Expected config keys:
            path:                 Model file path (e.g. "yolov8n.pt")
            confidence_threshold: Min confidence (e.g. 0.45)
            iou_threshold:        IOU for NMS (e.g. 0.45)
            device:               "auto", "cpu", or "cuda"
            detect_classes:       List of class names to detect
        """
        self.model_path: str = config.get("path", "yolov8n.pt")
        self.confidence: float = config.get("confidence_threshold", 0.45)
        self.iou_threshold: float = config.get("iou_threshold", 0.45)
        self.device_cfg: str = config.get("device", "auto")
        self.model = None
        self.device: str = "cpu"

        # Build list of target class IDs from config class names
        configured_names = config.get("detect_classes", list(ALL_TARGET_CLASSES.values()))
        self.target_ids: List[int] = [
            cid for cid, name in ALL_TARGET_CLASSES.items()
            if name in configured_names
        ]

        # Performance tracking
        self._last_inference_ms: float = 0.0
        self._total_detections: int = 0
        self._frames_processed: int = 0

        logger.info(f"Detector initialized | model={self.model_path} | conf={self.confidence}")
        logger.info(f"Target classes: {[ALL_TARGET_CLASSES[i] for i in self.target_ids]}")

    def load(self) -> bool:
        """
        Load the YOLO model into memory.

        This is called once at startup. The model file is downloaded
        automatically if it doesn't exist locally.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        try:
            from ultralytics import YOLO  # type: ignore

            # Resolve device
            self.device = self._resolve_device()
            logger.info(f"Using device: {self.device.upper()}")

            # Load model (auto-downloads if not found locally)
            model_path = self.model_path
            if not Path(model_path).exists():
                logger.info(
                    f"Model '{model_path}' not found locally. "
                    "Ultralytics will download it automatically..."
                )

            logger.info(f"Loading YOLO model: {model_path}")
            self.model = YOLO(model_path)

            # Move to correct device
            if self.device != "cpu":
                self.model.to(self.device)

            logger.info(f"Model loaded successfully: {model_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model '{self.model_path}': {e}")
            return False

    def detect(
        self,
        frame: np.ndarray,
        frame_number: int = 0,
        camera_id: str = "camera_001",
    ) -> List[DetectionResult]:
        """
        Run YOLO detection on a single frame.

        Args:
            frame:        BGR image array from OpenCV (H x W x 3)
            frame_number: Frame index in the video (for logging)
            camera_id:    Which camera this frame is from

        Returns:
            List of DetectionResult objects (one per detected object)

        Example:
            frame = cv2.imread("image.jpg")
            detections = detector.detect(frame, frame_number=1, camera_id="cam_01")
            for d in detections:
                print(f"{d.class_name}: {d.confidence:.0%} at {d.bbox}")
        """
        if self.model is None:
            logger.error("Model not loaded! Call detector.load() first.")
            return []

        if frame is None or frame.size == 0:
            logger.warning(f"Empty frame received at frame {frame_number}")
            return []

        detections: List[DetectionResult] = []

        try:
            t_start = time.time()

            # Run YOLO inference
            # verbose=False suppresses YOLO's own console output
            results = self.model(
                frame,
                conf=self.confidence,
                iou=self.iou_threshold,
                classes=self.target_ids,     # Only detect our target classes
                verbose=False,
                device=self.device,
            )

            self._last_inference_ms = (time.time() - t_start) * 1000
            self._frames_processed += 1

            # Parse YOLO results into our DetectionResult format
            for result in results:
                if result.boxes is None:
                    continue

                for box in result.boxes:
                    class_id   = int(box.cls[0])
                    confidence = float(box.conf[0])
                    # box.xyxy gives [x1, y1, x2, y2] as float tensor
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    bbox = [x1, y1, x2, y2]

                    det = make_detection(
                        class_id=class_id,
                        confidence=confidence,
                        bbox=bbox,
                        frame_number=frame_number,
                        camera_id=camera_id,
                    )

                    if det is not None:
                        detections.append(det)
                        self._total_detections += 1

            if detections:
                logger.debug(
                    f"Frame {frame_number}: {len(detections)} detections "
                    f"in {self._last_inference_ms:.1f}ms"
                )

        except Exception as e:
            logger.error(f"Detection error on frame {frame_number}: {e}")

        return detections

    def is_loaded(self) -> bool:
        """Return True if the model has been loaded successfully."""
        return self.model is not None

    @property
    def inference_ms(self) -> float:
        """Time taken for the last inference in milliseconds."""
        return self._last_inference_ms

    @property
    def total_detections(self) -> int:
        """Total number of detections across all processed frames."""
        return self._total_detections

    @property
    def frames_processed(self) -> int:
        """Total number of frames processed."""
        return self._frames_processed

    def get_stats(self) -> dict:
        """Return performance statistics."""
        return {
            "model_path":         self.model_path,
            "device":             self.device,
            "confidence":         self.confidence,
            "frames_processed":   self._frames_processed,
            "total_detections":   self._total_detections,
            "last_inference_ms":  round(self._last_inference_ms, 2),
        }

    def _resolve_device(self) -> str:
        """
        Determine which compute device to use.

        Returns:
            "cuda" if GPU is available and config says "auto" or "cuda",
            "cpu" otherwise.
        """
        if self.device_cfg == "cpu":
            return "cpu"

        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"GPU detected: {gpu_name} — using CUDA")
                return "cuda"
            else:
                logger.info("No GPU detected — using CPU")
                return "cpu"
        except ImportError:
            logger.warning("PyTorch not available for GPU check — using CPU")
            return "cpu"
