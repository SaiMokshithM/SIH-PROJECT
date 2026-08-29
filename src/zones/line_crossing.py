"""
src/zones/line_crossing.py
===========================
PURPOSE:
    Detects when a tracked object crosses a configured virtual line.

    A virtual line is a straight line segment defined by two points:
        start: [x1, y1]
        end:   [x2, y2]

    When an object's center crosses this line:
        → VIRTUAL_FENCE_CROSSING event

    Crossing direction can be:
        IN    = crossing from outside to inside
        OUT   = crossing from inside to outside
        BOTH  = detect in either direction

CONCEPT — Line Crossing Detection:
    We track which "side" of the line each object was on in the previous frame.
    If the side changes → the object crossed the line.

    Mathematical approach:
    Given a line from A to B, and a point P:
    Compute the cross product: (B-A) × (P-A)
    Positive = left side, Negative = right side, Zero = on line.

    If the sign flips between frames → crossing detected.

HOW TO USE:
    from src.zones.line_crossing import LineCrossingDetector

    lcd = LineCrossingDetector(config)
    lcd.load_lines("config/cameras.yaml")  # lines stored in cameras.yaml

    events = lcd.update(tracks, camera_id="camera_001", frame_number=100)
"""

from typing import List, Dict, Tuple, Optional
import yaml
from pathlib import Path

from src.tracking.track import Track
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts
from src.utils.logger import get_logger

logger = get_logger(__name__)


class VirtualLine:
    """Represents one virtual fence line."""

    def __init__(
        self,
        line_id: str,
        name: str,
        start: List[int],
        end: List[int],
        direction: str = "BOTH",
        camera_id: Optional[str] = None,
        color: Tuple[int, int, int] = (0, 255, 255),
    ):
        self.line_id = line_id
        self.name = name
        self.start = start
        self.end = end
        self.direction = direction.upper()   # "IN", "OUT", or "BOTH"
        self.camera_id = camera_id
        self.color = color  # BGR color for drawing (default: cyan)

    def side_of_point(self, px: int, py: int) -> float:
        """
        Compute which side of the line a point is on.

        Uses 2D cross product: (B-A) × (P-A)
        Positive = left side of line from A→B
        Negative = right side
        Zero = on the line

        Returns:
            float: positive, negative, or zero
        """
        ax, ay = self.start
        bx, by = self.end
        # Cross product: (B-A) × (P-A)
        return float((bx - ax) * (py - ay) - (by - ay) * (px - ax))

    def __repr__(self) -> str:
        return f"VirtualLine(id={self.line_id!r}, {self.start}→{self.end}, dir={self.direction})"


class LineCrossingDetector:
    """
    Detects virtual fence crossings for tracked objects.

    Maintains the "previous side" of each line for each track.
    When the side flips, a VIRTUAL_FENCE_CROSSING event is generated.

    Attributes:
        lines:          List of VirtualLine objects
        _prev_side:     Dict[(track_id, line_id), float] — last cross product sign
        _cooldown:      Seconds between crossing events for same (track, line)
        _last_fire:     Dict[(track_id, line_id), float] — last event time
    """

    def __init__(self, config: dict):
        self.config = config
        self.lines: List[VirtualLine] = []
        self._prev_side: Dict[Tuple[int, str], float] = {}
        self._cooldown: float = config.get("events", {}).get("cooldown_seconds", 5.0)
        self._last_fire: Dict[Tuple, float] = {}
        logger.info("LineCrossingDetector initialized")

    def load_lines(self, cameras_file: str = "config/cameras.yaml") -> int:
        """
        Load virtual line definitions from cameras.yaml.

        Args:
            cameras_file: Path to cameras.yaml

        Returns:
            Number of virtual lines loaded
        """
        path = Path(cameras_file)
        if not path.exists():
            logger.warning(f"Cameras file not found: {cameras_file}")
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            raw_lines = data.get("virtual_lines", []) if data else []
            self.lines = []

            for vl in raw_lines:
                if not vl.get("enabled", True):
                    continue

                pts = vl.get("points", [])
                if len(pts) < 2:
                    logger.warning(f"Virtual line {vl.get('id')} needs exactly 2 points — skipped")
                    continue

                line = VirtualLine(
                    line_id=vl["id"],
                    name=vl.get("name", vl["id"]),
                    start=pts[0],
                    end=pts[1],
                    direction=vl.get("direction", "BOTH"),
                    camera_id=vl.get("camera_id", None),
                    color=tuple(vl.get("color_bgr", [0, 255, 255])),
                )
                self.lines.append(line)
                logger.info(
                    f"Virtual line loaded: [{line.line_id}] {line.name!r} "
                    f"| {line.start}→{line.end} | dir={line.direction}"
                )

            logger.info(f"Total virtual lines loaded: {len(self.lines)}")
            return len(self.lines)

        except Exception as e:
            logger.error(f"Failed to load virtual lines from {cameras_file}: {e}")
            return 0

    def update(
        self,
        tracks: List[Track],
        camera_id: str,
        frame_number: int = 0,
    ) -> List[AIEvent]:
        """
        Check all tracks against all virtual lines for crossings.

        Args:
            tracks:       List of active Track objects
            camera_id:    Camera identifier
            frame_number: Current frame number

        Returns:
            List of AIEvent objects for crossings this frame
        """
        if not self.lines:
            return []

        events: List[AIEvent] = []
        now = now_ts()
        seen_track_ids = {t.track_id for t in tracks}

        # Filter lines for this camera
        active_lines = [
            line for line in self.lines
            if line.camera_id is None or line.camera_id == camera_id
        ]

        for track in tracks:
            if not track.is_confirmed:
                continue

            tid = track.track_id
            cx, cy = track.center

            for line in active_lines:
                key = (tid, line.line_id)
                current_side = line.side_of_point(cx, cy)
                prev_side = self._prev_side.get(key)

                if prev_side is not None and prev_side != 0 and current_side != 0:
                    # Check if side changed (crossing occurred)
                    if (prev_side > 0) != (current_side > 0):
                        # Determine crossing direction
                        if prev_side > 0 and current_side < 0:
                            cross_dir = "IN"
                        else:
                            cross_dir = "OUT"

                        # Filter by configured direction
                        if line.direction == "BOTH" or line.direction == cross_dir:
                            # Check cooldown
                            last = self._last_fire.get(key, 0.0)
                            if (now - last) >= self._cooldown:
                                evt = self._make_crossing_event(
                                    track, line, cross_dir, camera_id, frame_number
                                )
                                events.append(evt)
                                self._last_fire[key] = now
                                logger.info(
                                    f"FENCE CROSSING | track={tid} ({track.class_name}) "
                                    f"| line={line.line_id} | dir={cross_dir}"
                                )

                self._prev_side[key] = current_side

        # Clean up deleted tracks
        for tid in list(set(k[0] for k in self._prev_side)):
            if tid not in seen_track_ids:
                for line in self.lines:
                    self._prev_side.pop((tid, line.line_id), None)

        return events

    def _make_crossing_event(
        self,
        track: Track,
        line: VirtualLine,
        direction: str,
        camera_id: str,
        frame_number: int,
    ) -> AIEvent:
        desc = (
            f"{track.class_name.title()} (ID {track.track_id}) "
            f"crossed virtual fence '{line.name}' "
            f"(direction: {direction}). Requires authorized review."
        )
        return AIEvent(
            event_type=EventType.VIRTUAL_FENCE_CROSSING,
            camera_id=camera_id,
            severity=Severity.HIGH,
            risk_score=60,
            track_id=track.track_id,
            object_type=track.category,
            object_class=track.class_name,
            confidence=track.confidence,
            bbox=list(track.bbox),
            center=list(track.center),
            line_id=line.line_id,
            zone_name=line.name,
            movement_state=track.movement_state.value,
            direction=direction,
            frame_number=frame_number,
            description=desc,
            model_name="YOLOv8",
        )

    def draw_lines(self, frame, scale: float = 1.0) -> None:
        """
        Draw all virtual lines on the frame.

        Args:
            frame: BGR image to draw on
            scale: Scale factor if frame was resized
        """
        import cv2

        for line in self.lines:
            x1 = int(line.start[0] * scale)
            y1 = int(line.start[1] * scale)
            x2 = int(line.end[0] * scale)
            y2 = int(line.end[1] * scale)

            # Draw thick dashed line
            cv2.line(frame, (x1, y1), (x2, y2), line.color, 3)

            # Arrow to show direction
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.arrowedLine(frame, (mx, my), (mx + 20, my - 15), line.color, 2)

            # Label
            cv2.putText(
                frame, f"FENCE: {line.name}",
                (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, line.color, 2
            )
