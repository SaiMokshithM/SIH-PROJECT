"""
src/faces/face_detector.py
===========================
PURPOSE:
    Detects faces in video frames and SAVES face images to output folder.

    IMPORTANT:
    This module performs FACE DETECTION only.
    It does NOT identify who the person is.
    It does NOT create biometric profiles.
    It does NOT perform recognition or matching.

    Output:
    - Bounding box of detected face
    - Confidence score
    - Associated person track ID (if person track overlaps)
    - Face crop JPEG saved to: data/output/faces/
    - Annotated full-frame JPEG saved alongside the crop
    - Optional: blur face in displayed frame (privacy mode)

TECHNOLOGY:
    Primary: OpenCV Haar Cascade (built-in, no extra install)
    Better:  pip install opencv-contrib-python  (same Haar, but more cascades)
    Best:    YOLOv8-face model (place at models/face/yolov8n-face.pt)

FACE IMAGE FILES SAVED:
    data/output/faces/
    ├── face_0001_trk5_20260830_005201.jpg   ← cropped face only
    ├── face_0001_trk5_20260830_005201_ctx.jpg ← full frame with box drawn
    └── faces_log.jsonl                       ← JSON record of every face
"""

import cv2
import json
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional
from dataclasses import dataclass

from src.tracking.track import Track
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts, now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Padding around face crop (pixels)
CROP_PADDING = 20


@dataclass
class FaceDetection:
    """One detected face."""
    bbox: List[int]                    # [x1, y1, x2, y2]
    confidence: float
    center: List[int]
    associated_track_id: Optional[int] = None
    camera_id: str = ""
    timestamp: str = ""
    frame_number: int = 0
    face_image_path: Optional[str] = None     # path to saved face crop
    context_image_path: Optional[str] = None  # path to saved full-frame context

    def to_dict(self) -> dict:
        return {
            "event_type":        "FACE_DETECTED",
            "camera_id":         self.camera_id,
            "track_id":          self.associated_track_id,
            "confidence":        round(self.confidence, 4),
            "bbox":              self.bbox,
            "center":            self.center,
            "timestamp":         self.timestamp,
            "frame_number":      self.frame_number,
            "face_image":        self.face_image_path,
            "context_image":     self.context_image_path,
            "note":              "Face detection only. No identification performed.",
        }


class FaceDetector:
    """
    Detects faces using OpenCV Haar Cascade (or YOLOv8-face if available).

    Saves every detected face as:
    1. A cropped JPEG of just the face region
    2. A context JPEG of the full frame with the face box drawn
    3. A JSONL log file with all detection metadata

    Privacy-safe: detection bounding boxes only.
    No identity, no demographics, no recognition.
    """

    def __init__(self, config: dict):
        face_cfg             = config.get("face_detection", {})
        self.enabled: bool   = face_cfg.get("enabled", True)
        self.blur_faces: bool = config.get("privacy", {}).get("blur_faces", False)
        self.scale_factor: float = face_cfg.get("scale_factor", 1.1)
        self.min_neighbors: int  = face_cfg.get("min_neighbors", 5)
        self.min_size: Tuple[int, int] = tuple(face_cfg.get("min_size", [30, 30]))
        self._cooldown: float    = config.get("events", {}).get("cooldown_seconds", 10.0)
        self._last_event: dict   = {}
        self._cascade            = None
        self._yolo_model         = None
        self._use_yolo           = False
        self._face_counter: int  = 0

        # Output directory for face images
        base_out = config.get("output", {}).get("base_dir", "data/output")
        self.face_output_dir = Path(base_out) / "faces"
        self.face_output_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.face_output_dir / "faces_log.jsonl"

        # Config: whether to save images
        self.save_face_images: bool    = face_cfg.get("save_face_images", True)
        self.save_context_images: bool = face_cfg.get("save_context_images", True)
        self.jpeg_quality: int         = face_cfg.get("jpeg_quality", 92)

        if self.enabled:
            self._load_detector()

    def _load_detector(self) -> None:
        """Load Haar Cascade or YOLO face model."""
        # Try YOLO face model first (best accuracy)
        yolo_path = Path("models/face/yolov8n-face.pt")
        if yolo_path.exists():
            try:
                from ultralytics import YOLO
                self._yolo_model = YOLO(str(yolo_path))
                self._use_yolo = True
                logger.info("Face detector: YOLOv8-face model loaded")
                return
            except Exception as e:
                logger.warning(f"YOLO face model failed: {e} — falling back to Haar")

        # Look for Haar cascade XML — check local models/ dir first,
        # then fall back to what's inside the opencv package
        cascade_candidates = [
            Path("models/face/haarcascade_frontalface_default.xml"),  # our downloaded copy
        ]
        try:
            # OpenCV package may or may not have data dir with cascade files
            import cv2 as _cv2
            if hasattr(_cv2, "data") and _cv2.data.haarcascades:
                cascade_candidates.append(
                    Path(_cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
                )
        except Exception:
            pass

        cascade_path = None
        for candidate in cascade_candidates:
            if candidate.exists() and candidate.stat().st_size > 10_000:
                cascade_path = str(candidate)
                break

        if cascade_path is None:
            logger.warning(
                "Face detector: No Haar cascade file found.\n"
                "  Auto-fix: Run this once to download it:\n"
                "    python -c \"import urllib.request,pathlib; pathlib.Path('models/face').mkdir(parents=True,exist_ok=True); urllib.request.urlretrieve('https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml','models/face/haarcascade_frontalface_default.xml')\"\n"
                "  Face detection DISABLED for this session."
            )
            self.enabled = False
            return

        try:
            cascade = cv2.CascadeClassifier(cascade_path)
            if cascade.empty():
                raise ValueError(f"Cascade is empty: {cascade_path}")
            self._cascade = cascade
            logger.info(f"Face detector: Haar Cascade loaded from {cascade_path}")
            logger.info(f"  Face images will be saved to: {self.face_output_dir}")
        except AttributeError:
            logger.warning("Face detector: cv2.CascadeClassifier not available — disabled.")
            self.enabled = False
        except Exception as e:
            logger.warning(f"Face detector: Haar cascade failed ({e}) — disabled.")
            self.enabled = False


    def detect(
        self,
        frame: np.ndarray,
        tracks: List[Track],
        camera_id: str,
        frame_number: int,
    ) -> Tuple[List[FaceDetection], List[AIEvent]]:
        """
        Detect faces, save face images, and generate FACE_DETECTED events.

        Saved files per detected face (with cooldown applied):
            face_NNNN_trkID_TIMESTAMP.jpg      ← Face crop
            face_NNNN_trkID_TIMESTAMP_ctx.jpg  ← Full frame context

        Args:
            frame:        BGR image
            tracks:       Current active tracks for association
            camera_id:    Camera ID for events
            frame_number: Current frame number

        Returns:
            (face_detections, events) tuple
        """
        if not self.enabled:
            return [], []

        faces  = self._run_detection(frame)
        events = []
        now    = now_ts()

        for face in faces:
            face.camera_id    = camera_id
            face.frame_number = frame_number
            face.timestamp    = now_iso()
            face.associated_track_id = self._associate_track(face, tracks)

            # Apply blur to display frame if privacy mode
            if self.blur_faces:
                self._blur_face(frame, face.bbox)

            # Cooldown check — only save + event once per N seconds per track
            tid  = face.associated_track_id or -1
            last = self._last_event.get((tid, camera_id), 0.0)
            if (now - last) < self._cooldown:
                continue

            # ── Save face images ────────────────────────────────────────
            if self.save_face_images or self.save_context_images:
                self._face_counter += 1
                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                stem   = f"face_{self._face_counter:04d}_trk{tid}_{ts_str}"

                if self.save_face_images:
                    face.face_image_path = self._save_face_crop(frame, face.bbox, stem)

                if self.save_context_images:
                    face.context_image_path = self._save_context(
                        frame, face, stem, camera_id, frame_number
                    )

                # Write to JSONL log
                self._write_log(face)

                logger.info(
                    f"FACE SAVED | track={tid} | "
                    f"crop={face.face_image_path} | "
                    f"context={face.context_image_path}"
                )

            # ── Generate event ──────────────────────────────────────────
            evt = AIEvent(
                event_type=EventType.FACE_DETECTED,
                camera_id=camera_id,
                severity=Severity.INFO,
                track_id=face.associated_track_id,
                object_type="person",
                object_class="face",
                confidence=face.confidence,
                bbox=face.bbox,
                center=face.center,
                frame_number=frame_number,
                evidence_image=face.face_image_path,
                description=(
                    f"Face detected (detection only, no identification). "
                    f"Track: {face.associated_track_id}. "
                    f"Saved: {Path(face.face_image_path).name if face.face_image_path else 'N/A'}."
                ),
                model_name="Haar Cascade" if not self._use_yolo else "YOLOv8-face",
            )
            events.append(evt)
            self._last_event[(tid, camera_id)] = now

        return faces, events

    # ── Image saving helpers ────────────────────────────────────────────────

    def _save_face_crop(self, frame: np.ndarray, bbox: List[int], stem: str) -> Optional[str]:
        """Crop and save the face region with padding."""
        h, w   = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        # Add padding around face
        x1p = max(0, x1 - CROP_PADDING)
        y1p = max(0, y1 - CROP_PADDING)
        x2p = min(w, x2 + CROP_PADDING)
        y2p = min(h, y2 + CROP_PADDING)

        crop = frame[y1p:y2p, x1p:x2p]
        if crop.size == 0:
            return None

        path = self.face_output_dir / f"{stem}.jpg"
        cv2.imwrite(str(path), crop, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        return str(path)

    def _save_context(
        self,
        frame: np.ndarray,
        face: FaceDetection,
        stem: str,
        camera_id: str,
        frame_number: int,
    ) -> Optional[str]:
        """Save full frame with face box and labels drawn on it."""
        ctx = frame.copy()
        x1, y1, x2, y2 = face.bbox

        # Draw face box
        cv2.rectangle(ctx, (x1, y1), (x2, y2), (0, 230, 255), 2)

        # Label
        ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        label = f"FACE T:{face.associated_track_id or '?'}  {face.confidence:.0%}  {ts}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ly = max(y1, lh + 8)
        cv2.rectangle(ctx, (x1, ly - lh - 6), (x1 + lw + 4, ly + 2), (0, 230, 255), -1)
        cv2.putText(ctx, label, (x1 + 2, ly - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        # Metadata banner at top
        banner = f"Camera:{camera_id}  Frame:{frame_number}  DETECTION ONLY - NO ID"
        cv2.rectangle(ctx, (0, 0), (ctx.shape[1], 22), (0, 0, 0), -1)
        cv2.putText(ctx, banner, (4, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

        path = self.face_output_dir / f"{stem}_ctx.jpg"
        cv2.imwrite(str(path), ctx, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        return str(path)

    def _write_log(self, face: FaceDetection) -> None:
        """Append face detection metadata to faces_log.jsonl."""
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(face.to_dict()) + "\n")
        except Exception as e:
            logger.debug(f"Face log write error: {e}")

    # ── Detection backends ──────────────────────────────────────────────────

    def _run_detection(self, frame: np.ndarray) -> List[FaceDetection]:
        if self._use_yolo and self._yolo_model:
            return self._detect_yolo(frame)
        if self._cascade is not None:
            return self._detect_haar(frame)
        return []

    def _detect_haar(self, frame: np.ndarray) -> List[FaceDetection]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        rects = self._cascade.detectMultiScale(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
            minSize=self.min_size,
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        if len(rects) == 0:
            return []

        faces = []
        for (x, y, w, h) in rects:
            # Convert numpy int32 → plain Python int (required for JSON serialization)
            x, y, w, h = int(x), int(y), int(w), int(h)
            faces.append(FaceDetection(
                bbox=[x, y, x + w, y + h],
                confidence=0.75,
                center=[(2 * x + w) // 2, (2 * y + h) // 2],
            ))
        return faces

    def _detect_yolo(self, frame: np.ndarray) -> List[FaceDetection]:
        results = self._yolo_model(frame, verbose=False)
        faces = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                faces.append(FaceDetection(
                    bbox=[x1, y1, x2, y2],
                    confidence=conf,
                    center=[(x1 + x2) // 2, (y1 + y2) // 2],
                ))
        return faces

    def _associate_track(self, face: FaceDetection, tracks: List[Track]) -> Optional[int]:
        """Find the person track whose bounding box best overlaps the face."""
        fx1, fy1, fx2, fy2 = face.bbox
        best_overlap = 0.0
        best_id      = None

        for track in tracks:
            if track.category != "person" or not track.is_confirmed:
                continue
            tx1, ty1, tx2, ty2 = track.bbox
            iw = max(0, min(fx2, tx2) - max(fx1, tx1))
            ih = max(0, min(fy2, ty2) - max(fy1, ty1))
            inter = iw * ih
            if inter > best_overlap:
                best_overlap = inter
                best_id      = track.track_id

        return best_id

    def _blur_face(self, frame: np.ndarray, bbox: List[int]) -> None:
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        if x2 > x1 and y2 > y1:
            roi = frame[y1:y2, x1:x2]
            frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (51, 51), 30)

    def draw_faces(self, frame: np.ndarray, faces: List[FaceDetection]) -> None:
        """Draw face boxes on display frame."""
        for face in faces:
            x1, y1, x2, y2 = face.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 230, 255), 2)
            label = f"FACE {face.confidence:.0%}"
            if face.associated_track_id is not None:
                label += f" T:{face.associated_track_id}"
            cv2.putText(frame, label, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 230, 255), 1)

    @property
    def saved_count(self) -> int:
        """Total face images saved this session."""
        return self._face_counter
