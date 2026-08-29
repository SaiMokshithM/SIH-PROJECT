"""
src/events/event.py
====================
PURPOSE:
    Defines the AIEvent dataclass — the standard format for every alert
    this system produces.

    Every event (zone intrusion, slow movement, weapon detection, etc.)
    is represented as one AIEvent object and written to events.jsonl.

WHY A STANDARD FORMAT?
    The Spring Boot backend, React dashboard, and evidence capture system
    all need to understand event data. A single consistent format means
    no translation layer is needed between modules.

EXAMPLE EVENT:
    {
        "event_id":     "evt_000017",
        "event_type":   "RESTRICTED_ZONE_INTRUSION",
        "severity":     "HIGH",
        "risk_score":   75,
        "camera_id":    "camera_001",
        "timestamp":    "2026-08-29T23:20:01",
        "track_id":     5,
        "object_type":  "person",
        "movement_state": "SLOW",
        "direction":    "RIGHT",
        "zone_id":      "restricted_01",
        "description":  "Person entered configured restricted zone"
    }
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

from src.events.event_types import EventType, Severity, get_default_severity
from src.utils.time_utils import now_iso, now_ts


# ── Global event counter ───────────────────────────────────────────────────────
_event_counter: int = 0


def _next_event_id() -> str:
    """Generate a sequential, human-readable event ID."""
    global _event_counter
    _event_counter += 1
    return f"evt_{_event_counter:06d}"


def reset_event_counter() -> None:
    """Reset event counter (useful for testing)."""
    global _event_counter
    _event_counter = 0


@dataclass
class AIEvent:
    """
    A single analytics event produced by the AI engine.

    This is the core output unit of the system.
    Every detection, intrusion, behavioral alert, camera error,
    weapon detection, face detection, and ANPR result is one AIEvent.

    Required fields:
        event_type:   What happened (EventType enum)
        camera_id:    Which camera detected this

    Optional fields:
        All other fields are optional. Use None when not applicable.
        Never silently omit fields — always set them explicitly.

    Output format:
        Call .to_dict() to get a JSON-serializable dictionary.
    """

    # ── Required ───────────────────────────────────────────────────────────
    event_type: EventType
    camera_id: str

    # ── Auto-generated ─────────────────────────────────────────────────────
    event_id: str = field(default_factory=_next_event_id)
    timestamp: str = field(default_factory=now_iso)
    timestamp_unix: float = field(default_factory=now_ts)

    # ── Severity & Risk ────────────────────────────────────────────────────
    severity: Optional[Severity] = None       # Auto-set from event_type if None
    risk_score: int = 0                        # 0-100 operational priority score

    # ── Track / Object Info ────────────────────────────────────────────────
    track_id: Optional[int] = None
    object_type: Optional[str] = None         # "person", "vehicle", "animal"
    object_class: Optional[str] = None        # "person", "car", "dog", etc.
    confidence: Optional[float] = None

    # ── Location ───────────────────────────────────────────────────────────
    bbox: Optional[List[int]] = None           # [x1, y1, x2, y2]
    center: Optional[List[int]] = None         # [cx, cy]

    # ── Zone / Line ────────────────────────────────────────────────────────
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    line_id: Optional[str] = None

    # ── Movement ───────────────────────────────────────────────────────────
    movement_state: Optional[str] = None
    direction: Optional[str] = None
    pixel_speed: Optional[float] = None
    duration_seconds: Optional[float] = None

    # ── Evidence ───────────────────────────────────────────────────────────
    evidence_image: Optional[str] = None
    evidence_video: Optional[str] = None

    # ── Weapon / Face / ANPR specific ─────────────────────────────────────
    weapon_class: Optional[str] = None
    plate_text: Optional[str] = None
    plate_confidence: Optional[float] = None

    # ── Human-readable description ─────────────────────────────────────────
    description: str = ""

    # ── Model metadata ─────────────────────────────────────────────────────
    model_name: Optional[str] = None
    model_version: Optional[str] = None

    # ── Camera metadata ────────────────────────────────────────────────────
    camera_name: Optional[str] = None
    frame_number: Optional[int] = None

    # ── Internal lifecycle ─────────────────────────────────────────────────
    # Used for deduplication: NEW → ACTIVE → RESOLVED
    _state: str = field(default="NEW", repr=False)

    def __post_init__(self):
        """Auto-fill severity from default table if not provided."""
        if self.severity is None:
            self.severity = get_default_severity(self.event_type)

    def to_dict(self) -> dict:
        """
        Convert to a JSON-serializable dictionary.

        All None values are included explicitly (not silently dropped).
        This makes the format consistent for the Spring Boot backend.

        Returns:
            dict: All event fields as key-value pairs
        """
        return {
            # Core identity
            "event_id":       self.event_id,
            "event_type":     self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "severity":       self.severity.value if isinstance(self.severity, Severity) else self.severity,
            "risk_score":     self.risk_score,

            # Timing
            "timestamp":      self.timestamp,

            # Camera
            "camera_id":      self.camera_id,
            "camera_name":    self.camera_name,
            "frame_number":   self.frame_number,

            # Object
            "track_id":       self.track_id,
            "object_type":    self.object_type,
            "object_class":   self.object_class,
            "confidence":     round(self.confidence, 4) if self.confidence else None,

            # Location
            "bbox":           self.bbox,
            "center":         self.center,

            # Zone / Line
            "zone_id":        self.zone_id,
            "zone_name":      self.zone_name,
            "line_id":        self.line_id,

            # Movement
            "movement_state": self.movement_state,
            "direction":      self.direction,
            "pixel_speed":    round(self.pixel_speed, 2) if self.pixel_speed else None,
            "duration_seconds": round(self.duration_seconds, 1) if self.duration_seconds else None,

            # Evidence
            "evidence_image": self.evidence_image,
            "evidence_video": self.evidence_video,

            # Weapon / Face / ANPR
            "weapon_class":      self.weapon_class,
            "plate_text":        self.plate_text,
            "plate_confidence":  round(self.plate_confidence, 4) if self.plate_confidence else None,

            # Description
            "description":    self.description,

            # Model info
            "model_name":     self.model_name,
            "model_version":  self.model_version,
        }

    def __repr__(self) -> str:
        return (
            f"AIEvent("
            f"id={self.event_id}, "
            f"type={self.event_type.value}, "
            f"severity={self.severity.value if self.severity else 'None'}, "
            f"track={self.track_id}, "
            f"cam={self.camera_id})"
        )
