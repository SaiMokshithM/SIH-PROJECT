"""
src/behavior/movement_events.py
=================================
PURPOSE:
    Detects movement-based events for every tracked object:

    STATIONARY_OBJECT / PERSON_STATIONARY
        Object hasn't moved meaningfully for N configured seconds.

    SLOW_MOVEMENT_DETECTED
        Object has been in VERY_SLOW or SLOW state for N configured seconds.

    FAST_MOVEMENT_DETECTED
        Object's pixel speed exceeds the normal threshold.

HOW IT WORKS:
    For each track, we maintain a timer:
    - When the track enters STATIONARY state, we start a stationary timer.
    - When it has been stationary for stationary_threshold_seconds, generate event.
    - Same for slow movement.
    - For fast movement, generate immediately when speed crosses threshold.

EVENT DEDUPLICATION:
    We use a cooldown per (camera, track, event_type) combination.
    If the same event was generated within cooldown_seconds, skip it.
    This prevents flooding the output with repeated identical events.

HOW TO USE:
    from src.behavior.movement_events import MovementEventDetector

    detector = MovementEventDetector(config)
    events = detector.update(tracks, camera_id="camera_001", frame_number=100)
    for event in events:
        print(event)
"""

from typing import List, Dict, Tuple, Optional
from src.tracking.track import Track, MovementState
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MovementEventDetector:
    """
    Detects STATIONARY, SLOW, and FAST movement events from tracked objects.

    Maintains per-track timers and cooldowns to avoid duplicate events.

    Attributes:
        stationary_seconds:    Seconds before STATIONARY_OBJECT event
        slow_seconds:          Seconds before SLOW_MOVEMENT_DETECTED event
        fast_cooldown:         Cooldown (seconds) for FAST events per track
        general_cooldown:      Default cooldown between same events per track
    """

    def __init__(self, config: dict):
        """
        Initialize from config.

        Args:
            config: merged config dict (top-level from config.yaml)

        Reads:
            movement_events.stationary_threshold_seconds  (default 30)
            movement_events.slow_movement_seconds         (default 15)
            movement_events.fast_movement_cooldown        (default 10)
            events.cooldown_seconds                       (default 10)
        """
        me_cfg = config.get("movement_events", {})
        self.stationary_seconds: float = me_cfg.get("stationary_threshold_seconds", 30.0)
        self.slow_seconds: float = me_cfg.get("slow_movement_seconds", 15.0)
        self.fast_cooldown: float = me_cfg.get("fast_movement_cooldown", 10.0)
        self.general_cooldown: float = config.get("events", {}).get("cooldown_seconds", 10.0)

        # Per-track timers:
        # Key = track_id, Value = timestamp when track entered this state
        self._stationary_since: Dict[int, float] = {}
        self._slow_since: Dict[int, float] = {}

        # Cooldown tracker: Key = (track_id, event_type_value), Value = last event timestamp
        self._last_event_time: Dict[Tuple[int, str], float] = {}

        # Track which events have already fired (to avoid repeat logic)
        self._stationary_fired: Dict[int, bool] = {}
        self._slow_fired: Dict[int, bool] = {}

        logger.info(
            f"MovementEventDetector initialized | "
            f"stationary={self.stationary_seconds}s | "
            f"slow={self.slow_seconds}s | "
            f"fast_cooldown={self.fast_cooldown}s"
        )

    def update(
        self,
        tracks: List[Track],
        camera_id: str,
        frame_number: int = 0,
    ) -> List[AIEvent]:
        """
        Check all active tracks and generate movement events.

        Call this every frame after movement_analyzer.analyze() has run.

        Args:
            tracks:       List of active Track objects (already analyzed)
            camera_id:    Camera identifier for events
            frame_number: Current frame number

        Returns:
            List of AIEvent objects generated this frame (may be empty)
        """
        events: List[AIEvent] = []
        now = now_ts()

        # Track IDs seen this frame (for cleanup of old timers)
        seen_ids = {t.track_id for t in tracks}

        for track in tracks:
            if not track.is_confirmed:
                continue  # Only monitor confirmed tracks

            tid = track.track_id
            state = track.movement_state
            speed = getattr(track, "_pixel_speed", 0.0)

            # ── STATIONARY detection ───────────────────────────────────────
            if state == MovementState.STATIONARY:
                if tid not in self._stationary_since:
                    # Just became stationary
                    self._stationary_since[tid] = now
                    self._stationary_fired[tid] = False
                    logger.debug(f"Track {tid} ({track.class_name}) became STATIONARY")
                else:
                    # Already stationary — check how long
                    duration = now - self._stationary_since[tid]
                    if duration >= self.stationary_seconds and not self._stationary_fired.get(tid, False):
                        event = self._make_stationary_event(track, duration, camera_id, frame_number)
                        if event:
                            events.append(event)
                            self._stationary_fired[tid] = True
                            logger.info(
                                f"STATIONARY EVENT | track={tid} | "
                                f"class={track.class_name} | "
                                f"duration={duration:.1f}s"
                            )
            else:
                # Object is moving again — reset stationary timer
                if tid in self._stationary_since:
                    del self._stationary_since[tid]
                    self._stationary_fired.pop(tid, None)

            # ── SLOW MOVEMENT detection ────────────────────────────────────
            if state in (MovementState.VERY_SLOW, MovementState.SLOW):
                if tid not in self._slow_since:
                    self._slow_since[tid] = now
                    self._slow_fired[tid] = False
                else:
                    duration = now - self._slow_since[tid]
                    if duration >= self.slow_seconds and not self._slow_fired.get(tid, False):
                        event = self._make_slow_event(track, duration, speed, camera_id, frame_number)
                        if event:
                            events.append(event)
                            self._slow_fired[tid] = True
                            logger.info(
                                f"SLOW MOVEMENT EVENT | track={tid} | "
                                f"class={track.class_name} | "
                                f"duration={duration:.1f}s | speed={speed:.1f}px/f"
                            )
            else:
                # Speed changed — reset slow timer
                if tid in self._slow_since:
                    del self._slow_since[tid]
                    self._slow_fired.pop(tid, None)

            # ── FAST MOVEMENT detection ────────────────────────────────────
            if state == MovementState.FAST:
                if self._can_fire(tid, EventType.FAST_MOVEMENT_DETECTED, now, self.fast_cooldown):
                    event = self._make_fast_event(track, speed, camera_id, frame_number)
                    if event:
                        events.append(event)
                        self._record_fire(tid, EventType.FAST_MOVEMENT_DETECTED, now)
                        logger.info(
                            f"FAST MOVEMENT EVENT | track={tid} | "
                            f"class={track.class_name} | speed={speed:.1f}px/f"
                        )

        # ── Cleanup timers for deleted tracks ──────────────────────────────
        for tid in list(self._stationary_since.keys()):
            if tid not in seen_ids:
                del self._stationary_since[tid]
                self._stationary_fired.pop(tid, None)

        for tid in list(self._slow_since.keys()):
            if tid not in seen_ids:
                del self._slow_since[tid]
                self._slow_fired.pop(tid, None)

        return events

    # ── Event factory methods ──────────────────────────────────────────────────

    def _make_stationary_event(
        self,
        track: Track,
        duration: float,
        camera_id: str,
        frame_number: int,
    ) -> Optional[AIEvent]:
        """Create a STATIONARY_OBJECT or PERSON_STATIONARY event."""
        # Choose specific event type based on category
        if track.category == "person":
            event_type = EventType.PERSON_STATIONARY
            desc = f"Person (ID {track.track_id}) has been stationary for {duration:.0f} seconds."
        else:
            event_type = EventType.STATIONARY_OBJECT
            desc = (
                f"{track.class_name.title()} (ID {track.track_id}) "
                f"has been stationary for {duration:.0f} seconds."
            )

        return AIEvent(
            event_type=event_type,
            camera_id=camera_id,
            track_id=track.track_id,
            object_type=track.category,
            object_class=track.class_name,
            confidence=track.confidence,
            bbox=list(track.bbox),
            center=list(track.center),
            movement_state=track.movement_state.value,
            direction=track.direction.value,
            pixel_speed=getattr(track, "_pixel_speed", None),
            duration_seconds=duration,
            frame_number=frame_number,
            description=desc,
            model_name="YOLOv8",
        )

    def _make_slow_event(
        self,
        track: Track,
        duration: float,
        speed: float,
        camera_id: str,
        frame_number: int,
    ) -> Optional[AIEvent]:
        """Create a SLOW_MOVEMENT_DETECTED event."""
        desc = (
            f"{track.class_name.title()} (ID {track.track_id}) "
            f"has been moving slowly ({speed:.1f} px/frame) "
            f"for {duration:.0f} seconds. "
            f"NOTE: Slow movement is an analytical observation, not an indicator of intent."
        )
        return AIEvent(
            event_type=EventType.SLOW_MOVEMENT_DETECTED,
            camera_id=camera_id,
            track_id=track.track_id,
            object_type=track.category,
            object_class=track.class_name,
            confidence=track.confidence,
            bbox=list(track.bbox),
            center=list(track.center),
            movement_state=track.movement_state.value,
            direction=track.direction.value,
            pixel_speed=speed,
            duration_seconds=duration,
            frame_number=frame_number,
            description=desc,
            model_name="YOLOv8",
        )

    def _make_fast_event(
        self,
        track: Track,
        speed: float,
        camera_id: str,
        frame_number: int,
    ) -> Optional[AIEvent]:
        """Create a FAST_MOVEMENT_DETECTED event."""
        desc = (
            f"{track.class_name.title()} (ID {track.track_id}) "
            f"is moving fast ({speed:.1f} px/frame). "
            f"NOTE: Fast movement alone is not an indicator of danger."
        )
        return AIEvent(
            event_type=EventType.FAST_MOVEMENT_DETECTED,
            camera_id=camera_id,
            severity=Severity.MEDIUM,
            track_id=track.track_id,
            object_type=track.category,
            object_class=track.class_name,
            confidence=track.confidence,
            bbox=list(track.bbox),
            center=list(track.center),
            movement_state=track.movement_state.value,
            direction=track.direction.value,
            pixel_speed=speed,
            frame_number=frame_number,
            description=desc,
            model_name="YOLOv8",
        )

    # ── Cooldown helpers ───────────────────────────────────────────────────────

    def _can_fire(self, track_id: int, event_type: EventType, now: float, cooldown: float) -> bool:
        """Check if an event can be generated (i.e., cooldown has passed)."""
        key = (track_id, event_type.value)
        last = self._last_event_time.get(key, 0.0)
        return (now - last) >= cooldown

    def _record_fire(self, track_id: int, event_type: EventType, now: float) -> None:
        """Record that an event was just generated."""
        key = (track_id, event_type.value)
        self._last_event_time[key] = now
