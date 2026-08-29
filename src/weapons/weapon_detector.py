"""
src/weapons/weapon_detector.py
================================
PURPOSE:
    Weapon detection module — plug-in architecture.

    IMPORTANT:
    A general YOLO model trained on COCO CANNOT reliably detect weapons.
    This module requires a SPECIALIZED weapon-detection model trained
    on an authorized, legally-obtained dataset.

    Architecture:
        CCTV
         ↓
        General Object Detector  (YOLOv8 COCO)
         ↓
        Person / Vehicle / Animal detected
         ↓
        WeaponDetector  (separate specialized model)
         ↓
        POTENTIAL_WEAPON_DETECTED event
         ↓
        Human Review Alert

    Event naming:
        Always use POTENTIAL_WEAPON_DETECTED
        Never claim certainty unless model documentation justifies it.

    Use configurable confidence threshold:
        weapon_confidence_threshold: 0.60

HOW TO ADD A REAL MODEL:
    1. Obtain a legally authorized weapon dataset (academic/law enforcement)
    2. Train using training/train_detector.py with weapon dataset
    3. Place best.pt at models/weapon/weapon_detector.pt
    4. The system will auto-load it
    5. Set enabled: true in config.yaml under weapon_detection

STUB MODE:
    If no model file exists, the detector runs in STUB mode
    and logs a warning. No events are generated.
"""

import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

from src.tracking.track import Track
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts, now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Supported weapon classes from specialized model
# (actual classes depend on trained model — these are examples only)
WEAPON_CLASSES = [
    "knife", "handgun", "rifle", "pistol",
    "gun", "weapon", "blade", "firearm",
]


@dataclass
class WeaponDetection:
    """One potential weapon detection."""
    weapon_class: str
    confidence: float
    bbox: List[int]
    associated_track_id: Optional[int]
    camera_id: str = ""
    timestamp: str = ""
    frame_number: int = 0

    def to_dict(self) -> dict:
        return {
            "event_type":          "POTENTIAL_WEAPON_DETECTED",
            "weapon_class":        self.weapon_class,
            "confidence":          round(self.confidence, 4),
            "bbox":                self.bbox,
            "associated_track_id": self.associated_track_id,
            "camera_id":           self.camera_id,
            "timestamp":           self.timestamp,
            "frame_number":        self.frame_number,
            "note": (
                "This is a POTENTIAL detection requiring authorized human review. "
                "Do not treat as confirmed without expert verification."
            ),
        }


class WeaponDetector:
    """
    Plug-in architecture for specialized weapon detection.

    In STUB mode (no model file): logs warning, no detections.
    In ACTIVE mode (model loaded): runs inference, generates events.

    Attributes:
        enabled:        Config flag
        model_path:     Path to specialized weapon model weights
        min_confidence: Minimum confidence threshold (default 0.60)
        _model:         Loaded YOLO model or None
        _stub_mode:     True if no model loaded
    """

    def __init__(self, config: dict):
        wpn_cfg = config.get("weapon_detection", {})
        self.enabled: bool          = wpn_cfg.get("enabled", True)
        self.model_path: str        = wpn_cfg.get("model_path", "models/weapon/weapon_detector.pt")
        self.min_confidence: float  = wpn_cfg.get("weapon_confidence_threshold", 0.35)
        self._cooldown: float       = config.get("events", {}).get("cooldown_seconds", 15.0)
        self._last_event: dict      = {}
        self._model                 = None
        self._stub_mode             = True

        self._load_model()

    def _load_model(self) -> None:
        """Load specialized weapon detection model."""
        path = Path(self.model_path)
        if not path.exists():
            logger.warning(
                f"WeaponDetector: No model found at '{self.model_path}'."
            )
            self._stub_mode = True
            return

        try:
            from ultralytics import YOLO
            self._model = YOLO(str(path))
            self._stub_mode = False
            self.enabled = True
            logger.info(f"WeaponDetector: Model loaded from {self.model_path}")
        except Exception as e:
            logger.error(f"WeaponDetector: Failed to load model: {e}")
            self._stub_mode = True

    def detect_raw(self, frame: np.ndarray) -> List[Tuple[str, float, List[int]]]:
        """Detect weapons directly in a frame or uploaded image."""
        if self._stub_mode or self._model is None:
            return []
        items = []
        try:
            results = self._model(frame, conf=self.min_confidence, verbose=False)
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id   = int(box.cls[0])
                    cls_name = self._model.names.get(cls_id, "Gun")
                    conf     = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    if conf >= self.min_confidence:
                        items.append((cls_name, conf, [x1, y1, x2, y2]))
        except Exception as e:
            logger.error(f"WeaponDetector detect_raw error: {e}")
        return items

    def detect(
        self,
        frame: np.ndarray,
        person_tracks: List[Track],
        camera_id: str,
        frame_number: int,
    ) -> Tuple[List[WeaponDetection], List[AIEvent]]:
        """
        Run weapon detection on frame.

        Args:
            frame:         BGR video frame
            person_tracks: Person tracks (for association)
            camera_id:     Camera ID
            frame_number:  Frame number

        Returns:
            (weapon_detections, events) tuple
        """
        if not self.enabled or self._stub_mode or self._model is None:
            return [], []

        detections = []
        events     = []
        now        = now_ts()

        try:
            results = self._model(frame, conf=self.min_confidence, verbose=False)
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id   = int(box.cls[0])
                    cls_name = self._model.names.get(cls_id, "unknown")
                    conf     = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

                    if conf < self.min_confidence:
                        continue

                    # Associate with nearest person track
                    assoc_id = self._associate_person([x1, y1, x2, y2], person_tracks)

                    wd = WeaponDetection(
                        weapon_class=cls_name,
                        confidence=conf,
                        bbox=[x1, y1, x2, y2],
                        associated_track_id=assoc_id,
                        camera_id=camera_id,
                        timestamp=now_iso(),
                        frame_number=frame_number,
                    )
                    detections.append(wd)

                    # Cooldown check
                    key = (assoc_id or -1, camera_id, cls_name)
                    last = self._last_event.get(key, 0.0)
                    if (now - last) < self._cooldown:
                        continue

                    desc = (
                        f"POTENTIAL {cls_name.upper()} detected (conf: {conf:.0%}). "
                        f"Associated person track: {assoc_id}. "
                        f"REQUIRES IMMEDIATE AUTHORIZED HUMAN REVIEW. "
                        f"This is a potential detection, not a confirmed identification."
                    )
                    evt = AIEvent(
                        event_type=EventType.POTENTIAL_WEAPON_DETECTED,
                        camera_id=camera_id,
                        severity=Severity.HIGH,
                        risk_score=75,
                        track_id=assoc_id,
                        object_type="weapon",
                        object_class=cls_name,
                        confidence=conf,
                        bbox=[x1, y1, x2, y2],
                        weapon_class=cls_name,
                        frame_number=frame_number,
                        description=desc,
                        model_name="WeaponDetector-Custom",
                    )
                    events.append(evt)
                    self._last_event[key] = now
                    logger.warning(
                        f"POTENTIAL WEAPON | class={cls_name} | conf={conf:.0%} "
                        f"| track={assoc_id} | HUMAN REVIEW REQUIRED"
                    )

        except Exception as e:
            logger.error(f"WeaponDetector inference error: {e}")

        return detections, events

    def _associate_person(self, weapon_bbox: List[int], person_tracks: List[Track]) -> Optional[int]:
        """Find nearest confirmed person track to weapon bounding box."""
        wx1, wy1, wx2, wy2 = weapon_bbox
        wcx = (wx1 + wx2) // 2
        wcy = (wy1 + wy2) // 2
        best_dist = float("inf")
        best_id   = None

        for track in person_tracks:
            if track.category != "person" or not track.is_confirmed:
                continue
            tcx, tcy = track.center
            dist = ((wcx - tcx) ** 2 + (wcy - tcy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_id   = track.track_id

        return best_id
