"""
src/tracking/track.py
======================
PURPOSE:
    Defines the Track class — one entry per tracked object.

    A Track is like a "file" the system keeps for each object it follows.
    It stores the object's history: where it has been, how it moves,
    which zone it is in, how long it has been in the scene, etc.

CONCEPTS FOR BEGINNERS:
    - Track ID: A unique number (1, 2, 3...) assigned to each object.
      ID 17 = the 17th unique object seen in this session.
    - Trajectory: The list of past center positions of this object.
      Like breadcrumbs showing where the object has been.
    - Track State:
        TENTATIVE  = Just appeared, waiting for confirmation (min_hits frames)
        CONFIRMED  = Seen enough times — we trust it's real
        LOST       = Not detected for a few frames (may reappear)
        DELETED    = Gone too long — removed from memory
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum
import time

from src.utils.time_utils import now_ts, now_iso


class TrackState(Enum):
    """Lifecycle states of a tracked object."""
    TENTATIVE = "TENTATIVE"   # Newly appeared — not yet confirmed
    CONFIRMED = "CONFIRMED"   # Seen consistently — trusted track
    LOST      = "LOST"        # Missing for a few frames — may return
    DELETED   = "DELETED"     # Gone too long — remove from memory


class MovementState(Enum):
    """How fast an object is currently moving."""
    STATIONARY   = "STATIONARY"    # Barely moving
    VERY_SLOW    = "VERY_SLOW"     # Very slow movement
    SLOW         = "SLOW"          # Moving slowly
    NORMAL       = "NORMAL"        # Moving at normal speed
    FAST         = "FAST"          # Moving fast
    UNKNOWN      = "UNKNOWN"       # Not enough data yet


class Direction(Enum):
    """Movement direction in image/screen coordinates."""
    UP         = "UP"           # Moving toward top of frame
    DOWN       = "DOWN"         # Moving toward bottom of frame
    LEFT       = "LEFT"         # Moving toward left of frame
    RIGHT      = "RIGHT"        # Moving toward right of frame
    UP_LEFT    = "UP_LEFT"
    UP_RIGHT   = "UP_RIGHT"
    DOWN_LEFT  = "DOWN_LEFT"
    DOWN_RIGHT = "DOWN_RIGHT"
    STATIONARY = "STATIONARY"   # Not moving
    UNKNOWN    = "UNKNOWN"      # Not enough data


# Global track ID counter (increments for every new track)
_next_track_id: int = 1


def _get_next_id() -> int:
    """Get the next unique track ID."""
    global _next_track_id
    tid = _next_track_id
    _next_track_id += 1
    return tid


def reset_track_ids() -> None:
    """Reset track ID counter (useful for testing)."""
    global _next_track_id
    _next_track_id = 1


@dataclass
class Track:
    """
    Represents one tracked object across multiple frames.

    Attributes:
        track_id:       Unique integer ID for this track
        class_name:     Object class: "person", "car", "dog", etc.
        class_id:       COCO integer class ID
        category:       Broad category: "person", "vehicle", "animal"
        bbox:           Current bounding box [x1, y1, x2, y2]
        center:         Current center point [cx, cy]
        confidence:     Latest detection confidence score
        state:          Current TrackState (TENTATIVE/CONFIRMED/LOST/DELETED)
        first_seen:     Unix timestamp when first detected
        last_seen:      Unix timestamp of most recent detection
        hit_streak:     Consecutive frames with a detection
        frames_since_update: Frames since last detection (for LOST tracking)
        trajectory:     List of past center positions [[cx,cy], [cx,cy], ...]
        camera_id:      Which camera this track belongs to
        current_zone:   Zone ID the object is currently in (or None)
        previous_zone:  Zone ID the object was previously in (or None)
        movement_state: Current MovementState enum value
        direction:      Current Direction enum value
        color:          BGR color for visualization
    """

    class_name: str
    class_id: int
    category: str
    bbox: List[int]
    center: List[int]
    confidence: float
    camera_id: str = "camera_001"
    color: tuple = (0, 255, 0)
    max_trajectory_length: int = 30

    # Auto-assigned fields
    track_id: int = field(default_factory=_get_next_id)
    state: TrackState = TrackState.TENTATIVE
    first_seen: float = field(default_factory=now_ts)
    last_seen: float = field(default_factory=now_ts)
    hit_streak: int = 1
    frames_since_update: int = 0

    # Trajectory — list of [cx, cy] positions
    trajectory: List[List[int]] = field(default_factory=list)

    # Zone tracking
    current_zone: Optional[str] = None
    previous_zone: Optional[str] = None

    # Movement
    movement_state: MovementState = MovementState.UNKNOWN
    direction: Direction = Direction.UNKNOWN
    _pixel_speed: float = field(default=0.0, repr=False)

    # Previous center for displacement calculation
    _previous_center: Optional[List[int]] = field(default=None, repr=False)

    def __post_init__(self):
        """Called automatically after __init__ — adds initial position to trajectory."""
        if not self.trajectory:
            self.trajectory.append(list(self.center))

    # ── Update ─────────────────────────────────────────────────────

    def update(
        self,
        bbox: List[int],
        center: List[int],
        confidence: float,
        color: tuple = None,
    ) -> None:
        """
        Update track with a new detection from the current frame.

        Called when we match this track to a new detection.

        Args:
            bbox:       New bounding box [x1, y1, x2, y2]
            center:     New center point [cx, cy]
            confidence: New confidence score
            color:      New color (optional)
        """
        self._previous_center = list(self.center)
        self.bbox = bbox
        self.center = list(center)
        self.confidence = confidence
        if color:
            self.color = color
        self.last_seen = now_ts()
        self.hit_streak += 1
        self.frames_since_update = 0

        # Add to trajectory (keep only max_trajectory_length positions)
        self.trajectory.append(list(center))
        if len(self.trajectory) > self.max_trajectory_length:
            self.trajectory.pop(0)

    def mark_missed(self) -> None:
        """
        Called when no detection was matched to this track in a frame.
        Increments frames_since_update and resets hit_streak.
        """
        self.frames_since_update += 1
        self.hit_streak = 0

    # ── State transitions ──────────────────────────────────────────

    def confirm(self) -> None:
        """Promote track from TENTATIVE to CONFIRMED."""
        self.state = TrackState.CONFIRMED

    def mark_lost(self) -> None:
        """Mark track as LOST (missing for too many frames)."""
        self.state = TrackState.LOST

    def mark_deleted(self) -> None:
        """Mark track for deletion."""
        self.state = TrackState.DELETED

    # ── Computed properties ────────────────────────────────────────

    @property
    def time_in_scene(self) -> float:
        """How many seconds this object has been tracked (first to last seen)."""
        return self.last_seen - self.first_seen

    @property
    def time_in_scene_str(self) -> str:
        """Human-readable time in scene, e.g. '12.3s'"""
        return f"{self.time_in_scene:.1f}s"

    @property
    def is_confirmed(self) -> bool:
        return self.state == TrackState.CONFIRMED

    @property
    def is_tentative(self) -> bool:
        return self.state == TrackState.TENTATIVE

    @property
    def is_lost(self) -> bool:
        return self.state == TrackState.LOST

    @property
    def is_deleted(self) -> bool:
        return self.state == TrackState.DELETED

    @property
    def pixel_displacement(self) -> float:
        """
        Euclidean pixel distance moved since last frame.
        Returns 0.0 if no previous position available.
        """
        if self._previous_center is None:
            return 0.0
        dx = self.center[0] - self._previous_center[0]
        dy = self.center[1] - self._previous_center[1]
        return (dx ** 2 + dy ** 2) ** 0.5

    @property
    def bbox_width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def bbox_height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Convert track to a JSON-serializable dictionary."""
        return {
            "track_id":          self.track_id,
            "class_name":        self.class_name,
            "class_id":          self.class_id,
            "category":          self.category,
            "camera_id":         self.camera_id,
            "state":             self.state.value,
            "confidence":        round(self.confidence, 4),
            "bbox":              self.bbox,
            "center":            self.center,
            "first_seen":        now_iso(),
            "last_seen":         now_iso(),
            "time_in_scene_s":   round(self.time_in_scene, 2),
            "hit_streak":        self.hit_streak,
            "trajectory":        self.trajectory[-10:],  # Last 10 positions
            "current_zone":      self.current_zone,
            "previous_zone":     self.previous_zone,
            "movement_state":    self.movement_state.value,
            "direction":         self.direction.value,
            "pixel_displacement": round(self.pixel_displacement, 2),
        }

    def __repr__(self) -> str:
        return (
            f"Track(id={self.track_id}, class={self.class_name!r}, "
            f"state={self.state.value}, conf={self.confidence:.2f})"
        )
