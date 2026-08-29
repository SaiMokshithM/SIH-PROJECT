"""
src/movement/movement_analyzer.py
===================================
PURPOSE:
    Analyzes how every tracked object is moving.

    For every track, it calculates:
    - pixel_displacement: how far the center moved since last frame
    - direction: which way it's going (UP, DOWN, LEFT, etc.)
    - movement_state: STATIONARY / VERY_SLOW / SLOW / NORMAL / FAST

CONCEPTS FOR BEGINNERS:
    Displacement:
        If a person's center was at [100, 200] last frame
        and is now at [105, 210]:
        displacement = sqrt((105-100)^2 + (210-200)^2) = sqrt(25+100) = 11.2 pixels

    Direction:
        If the person moved RIGHT (+X) and DOWN (+Y):
        → direction = DOWN_RIGHT

        Image coordinates:
        (0,0) = top-left corner
        X increases going RIGHT
        Y increases going DOWN

        So "UP" in image space means the Y coordinate is DECREASING.
        We use image-coordinate names to avoid confusion with geographic north/south.

    Movement State:
        Based on pixel displacement per frame (configurable thresholds):
        < 1 pixel   → STATIONARY
        1-2 pixels  → VERY_SLOW
        2-5 pixels  → SLOW
        5-15 pixels → NORMAL
        > 15 pixels → FAST

HOW TO USE:
    from src.movement.movement_analyzer import MovementAnalyzer

    analyzer = MovementAnalyzer(config["movement"])
    for track in tracks:
        analyzer.analyze(track)
    # track.movement_state and track.direction are now updated
"""

import math
from typing import List, Optional
from src.tracking.track import Track, MovementState, Direction
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MovementAnalyzer:
    """
    Analyzes and updates movement state and direction for tracked objects.

    Reads configuration thresholds from config.yaml so they can be
    changed without editing Python code.

    Attributes:
        stationary_threshold:  Pixels/frame below which = STATIONARY
        very_slow_threshold:   Pixels/frame below which = VERY_SLOW
        slow_threshold:        Pixels/frame below which = SLOW
        normal_threshold:      Pixels/frame below which = NORMAL
        smoothing_frames:      Number of trajectory points to average
    """

    def __init__(self, config: dict):
        """
        Initialize movement analyzer from config.

        Args:
            config: 'movement' section from config.yaml

        Expected keys:
            stationary_threshold:   float (default 1.0)
            very_slow_threshold:    float (default 2.0)
            slow_threshold:         float (default 5.0)
            normal_threshold:       float (default 15.0)
            direction_smoothing_frames: int (default 5)
        """
        self.stationary_threshold: float = config.get("stationary_threshold", 1.0)
        self.very_slow_threshold:  float = config.get("very_slow_threshold",  2.0)
        self.slow_threshold:       float = config.get("slow_threshold",        5.0)
        self.normal_threshold:     float = config.get("normal_threshold",      15.0)
        self.smoothing_frames:     int   = config.get("direction_smoothing_frames", 5)

        logger.info(
            f"MovementAnalyzer initialized | "
            f"thresholds: stationary={self.stationary_threshold} "
            f"very_slow={self.very_slow_threshold} "
            f"slow={self.slow_threshold} "
            f"normal={self.normal_threshold}"
        )

    def analyze(self, track: Track) -> None:
        """
        Analyze movement for a single track and update it in place.

        This is called once per frame for every active track.
        It updates:
            - track.movement_state
            - track.direction
            - track._pixel_speed (set as attribute)

        Args:
            track: The Track object to analyze (modified in place)
        """
        if len(track.trajectory) < 2:
            # Not enough history yet
            track.movement_state = MovementState.UNKNOWN
            track.direction = Direction.UNKNOWN
            track._pixel_speed = 0.0
            return

        # ── Calculate displacement using smoothed trajectory ─────────
        displacement = self._calculate_displacement(track.trajectory)
        track._pixel_speed = displacement

        # ── Classify movement state ───────────────────────────────────
        track.movement_state = self._classify_speed(displacement)

        # ── Calculate direction ───────────────────────────────────────
        if track.movement_state == MovementState.STATIONARY:
            track.direction = Direction.STATIONARY
        else:
            track.direction = self._calculate_direction(track.trajectory)

    def _calculate_displacement(self, trajectory: List[List[int]]) -> float:
        """
        Calculate average pixel displacement using recent trajectory points.

        We average over the last N positions (smoothing_frames) to reduce
        noise from single-frame jitter.

        Args:
            trajectory: List of [cx, cy] positions (oldest first)

        Returns:
            float: Average displacement in pixels per frame
        """
        # Use the last N positions for smoothing
        n = min(self.smoothing_frames, len(trajectory))
        if n < 2:
            return 0.0

        recent = trajectory[-n:]
        total_displacement = 0.0

        for i in range(1, len(recent)):
            dx = recent[i][0] - recent[i-1][0]
            dy = recent[i][1] - recent[i-1][1]
            total_displacement += math.sqrt(dx * dx + dy * dy)

        return total_displacement / (len(recent) - 1)

    def _classify_speed(self, pixels_per_frame: float) -> MovementState:
        """
        Convert pixel displacement to a MovementState category.

        Args:
            pixels_per_frame: Average pixel displacement per frame

        Returns:
            MovementState enum value
        """
        if pixels_per_frame < self.stationary_threshold:
            return MovementState.STATIONARY
        elif pixels_per_frame < self.very_slow_threshold:
            return MovementState.VERY_SLOW
        elif pixels_per_frame < self.slow_threshold:
            return MovementState.SLOW
        elif pixels_per_frame < self.normal_threshold:
            return MovementState.NORMAL
        else:
            return MovementState.FAST

    def _calculate_direction(self, trajectory: List[List[int]]) -> Direction:
        """
        Estimate movement direction from recent trajectory.

        Uses the vector from the earliest recent point to the latest point.
        Then classifies it into 8 compass-like directions.

        Reminder: in image coordinates:
            X increases →  (RIGHT)
            Y increases ↓  (DOWN)

        Args:
            trajectory: List of [cx, cy] positions

        Returns:
            Direction enum value
        """
        n = min(self.smoothing_frames, len(trajectory))
        recent = trajectory[-n:]

        # Vector from oldest to newest position in the window
        dx = recent[-1][0] - recent[0][0]
        dy = recent[-1][1] - recent[0][1]

        if dx == 0 and dy == 0:
            return Direction.STATIONARY

        # Use atan2 to get angle in degrees
        # atan2(dy, dx): angle from positive X axis
        angle = math.degrees(math.atan2(dy, dx))

        # Map angle to 8-direction compass
        # angle 0° = RIGHT, 90° = DOWN, 180°/-180° = LEFT, -90° = UP
        return self._angle_to_direction(angle)

    def _angle_to_direction(self, angle: float) -> Direction:
        """
        Convert an angle (in degrees) to a Direction enum value.

        Angle reference:
            0°    = RIGHT
            45°   = DOWN_RIGHT
            90°   = DOWN
            135°  = DOWN_LEFT
            ±180° = LEFT
            -135° = UP_LEFT
            -90°  = UP
            -45°  = UP_RIGHT

        Args:
            angle: Angle in degrees from atan2

        Returns:
            Direction enum value
        """
        # Normalize to 0-360
        angle = angle % 360

        if 337.5 <= angle or angle < 22.5:
            return Direction.RIGHT
        elif 22.5 <= angle < 67.5:
            return Direction.DOWN_RIGHT
        elif 67.5 <= angle < 112.5:
            return Direction.DOWN
        elif 112.5 <= angle < 157.5:
            return Direction.DOWN_LEFT
        elif 157.5 <= angle < 202.5:
            return Direction.LEFT
        elif 202.5 <= angle < 247.5:
            return Direction.UP_LEFT
        elif 247.5 <= angle < 292.5:
            return Direction.UP
        elif 292.5 <= angle < 337.5:
            return Direction.UP_RIGHT
        else:
            return Direction.UNKNOWN

    def get_speed_description(self, track: Track) -> str:
        """
        Get a human-readable speed description for display or logging.

        Args:
            track: Track object (must have been analyzed already)

        Returns:
            str: e.g. "SLOW (3.2 px/frame)"
        """
        speed = getattr(track, "_pixel_speed", 0.0)
        state = track.movement_state.value
        return f"{state} ({speed:.1f} px/frame)"
