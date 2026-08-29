"""
src/zones/zone.py
==================
PURPOSE:
    Defines the Zone class — a named polygon region on the camera frame.

    A Zone is a list of [x, y] points that form a polygon.
    The system checks every tracked object against every zone
    to detect entries, exits, and intrusions.

CONCEPTS FOR BEGINNERS:
    Polygon: A shape made of straight lines connecting corner points.
    Example: A rectangle is a polygon with 4 corners.

    Zone Types:
        RESTRICTED    — No authorized entry. Triggers intrusion alert.
        HIGH_SECURITY — Highest security. Triggers critical alert.
        MONITORING    — Watch area. Logs all movement.
        ENTRY         — Designated entry point.
        EXIT          — Designated exit point.
        SAFE          — Safe zone. No alerts.

    Point-in-polygon (Ray Casting):
        Imagine shooting a ray to the right from the point.
        Count how many polygon edges the ray crosses.
        Odd count → INSIDE
        Even count → OUTSIDE

EXAMPLE zones.yaml:
    zones:
      - id: zone_001
        name: "Restricted Border Area"
        type: RESTRICTED
        polygon:
          - [100, 100]
          - [500, 100]
          - [500, 400]
          - [100, 400]
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


class ZoneType:
    """Zone type constants."""
    RESTRICTED    = "RESTRICTED"
    HIGH_SECURITY = "HIGH_SECURITY"
    MONITORING    = "MONITORING"
    ENTRY         = "ENTRY"
    EXIT          = "EXIT"
    SAFE          = "SAFE"


# BGR colors for drawing zones on frame
ZONE_COLORS = {
    ZoneType.RESTRICTED:    (0, 0, 200),
    ZoneType.HIGH_SECURITY: (0, 0, 255),
    ZoneType.MONITORING:    (0, 165, 255),
    ZoneType.ENTRY:         (0, 200, 0),
    ZoneType.EXIT:          (255, 100, 0),
    ZoneType.SAFE:          (100, 200, 100),
}

ZONE_ALPHA = {
    ZoneType.RESTRICTED:    0.08,   # Very subtle fill — border carries the color
    ZoneType.HIGH_SECURITY: 0.12,
    ZoneType.MONITORING:    0.05,
    ZoneType.ENTRY:         0.05,
    ZoneType.EXIT:          0.05,
    ZoneType.SAFE:          0.03,
}


@dataclass
class Zone:
    """
    A named polygon zone on the camera frame.

    Attributes:
        zone_id:        Unique identifier (e.g., "zone_001")
        name:           Human-readable name (e.g., "North Restricted Area")
        zone_type:      ZoneType string ("RESTRICTED", "MONITORING", etc.)
        polygon:        List of [x, y] corner points
        enabled:        Whether zone checking is active
        camera_id:      Which camera this zone belongs to (None = all cameras)
        loitering_threshold_seconds: Override for loitering timer (None = use global default)
        color:          BGR color for visualization
        alpha:          Transparency for fill (0.0 = transparent, 1.0 = opaque)
    """
    zone_id: str
    name: str
    zone_type: str
    polygon: List[List[int]]
    enabled: bool = True
    camera_id: Optional[str] = None
    loitering_threshold_seconds: Optional[float] = None
    color: Tuple[int, int, int] = field(default=(0, 0, 200))
    alpha: float = 0.25

    def __post_init__(self):
        """Set color and alpha based on zone type."""
        self.color = ZONE_COLORS.get(self.zone_type, (128, 128, 128))
        self.alpha = ZONE_ALPHA.get(self.zone_type, 0.15)

    def get_scaled_polygon(self, frame_w: int = 640, frame_h: int = 480) -> List[List[int]]:
        """Scale polygon points to current frame dimensions."""
        if not self.polygon or len(self.polygon) < 3:
            return []
        
        # Check if polygon is normalized (all points <= 1.0)
        is_normalized = all(p[0] <= 1.0 and p[1] <= 1.0 for p in self.polygon)
        if is_normalized:
            return [[int(p[0] * frame_w), int(p[1] * frame_h)] for p in self.polygon]

        # If defined in base 640x480 coordinate space, scale to actual frame
        if frame_w > 0 and frame_h > 0 and (frame_w != 640 or frame_h != 480):
            sx = frame_w / 640.0
            sy = frame_h / 480.0
            return [[int(p[0] * sx), int(p[1] * sy)] for p in self.polygon]

        return [[int(p[0]), int(p[1])] for p in self.polygon]

    def contains_point(self, x: int, y: int, frame_w: int = 640, frame_h: int = 480) -> bool:
        """
        Check if point (x, y) is inside this zone's polygon.
        Uses the Ray Casting algorithm.
        """
        poly = self.get_scaled_polygon(frame_w, frame_h) if (frame_w and frame_h) else self.polygon
        if len(poly) < 3:
            return False

        inside = False
        n = len(poly)
        j = n - 1

        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]

            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside

            j = i

        return inside

    def contains_track(self, track, frame_w: int = 640, frame_h: int = 480) -> bool:
        """
        Check if a track is in this zone.
        Checks center point, bottom-center (feet), and bbox corners for responsive detection.
        """
        cx, cy = track.center
        if self.contains_point(cx, cy, frame_w, frame_h):
            return True

        # Check feet / bottom-center
        x1, y1, x2, y2 = track.bbox
        if self.contains_point(cx, y2, frame_w, frame_h):
            return True
        
        # Check midpoint of left and right edges
        if self.contains_point(x1, cy, frame_w, frame_h) or self.contains_point(x2, cy, frame_w, frame_h):
            return True

        return False

    def contains_center(self, center: List[int], frame_w: int = 640, frame_h: int = 480) -> bool:
        """Check if center point is inside this zone."""
        return self.contains_point(center[0], center[1], frame_w, frame_h)

    @property
    def is_restricted(self) -> bool:
        return self.zone_type in (ZoneType.RESTRICTED, ZoneType.HIGH_SECURITY)

    @property
    def is_high_security(self) -> bool:
        return self.zone_type == ZoneType.HIGH_SECURITY

    def to_dict(self) -> dict:
        return {
            "zone_id":   self.zone_id,
            "name":      self.name,
            "type":      self.zone_type,
            "polygon":   self.polygon,
            "enabled":   self.enabled,
            "camera_id": self.camera_id,
        }

    def __repr__(self) -> str:
        return f"Zone(id={self.zone_id!r}, type={self.zone_type}, points={len(self.polygon)})"
