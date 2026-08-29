"""
src/behavior/unusual_movement.py
==================================
PURPOSE:
    Detects unusual movement patterns using configurable rules.

    Detected patterns:
    1. SUDDEN_DIRECTION_CHANGE   — direction changes sharply within N frames
    2. SUDDEN_SPEED_CHANGE       — speed jumps/drops dramatically
    3. BACK_AND_FORTH            — object repeatedly reverses direction
    4. STATIONARY_TO_FAST        — sudden sprint from standstill
    5. REPEATED_ZONE_ENTRY       — enters same zone multiple times

    Generates: UNUSUAL_MOVEMENT_DETECTED

    IMPORTANT:
    No single unusual movement event should be interpreted as suspicious.
    The event description always contains a plain factual explanation.
    The risk engine may combine multiple signals to compute a risk score.
"""

from typing import List, Dict, Deque, Optional
from collections import deque, Counter
from src.tracking.track import Track, MovementState, Direction
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Direction groups for "opposite" detection
DIRECTION_OPPOSITES = {
    "RIGHT": "LEFT", "LEFT": "RIGHT",
    "UP": "DOWN", "DOWN": "UP",
    "UP_RIGHT": "DOWN_LEFT", "DOWN_LEFT": "UP_RIGHT",
    "UP_LEFT": "DOWN_RIGHT", "DOWN_RIGHT": "UP_LEFT",
}


class UnusualMovementDetector:
    """
    Rule-based unusual movement pattern detector.

    Maintains recent movement history per track and applies rules.

    Attributes:
        history_frames:  How many frames of movement history to keep
        _dir_history:    Dict[track_id, deque of direction strings]
        _speed_history:  Dict[track_id, deque of float speeds]
        _zone_history:   Dict[track_id, deque of zone_id strings]
    """

    def __init__(self, config: dict):
        umu_cfg = config.get("unusual_movement", {})
        self.enabled: bool          = umu_cfg.get("enabled", True)
        self.history_frames: int    = umu_cfg.get("history_frames", 30)
        self.dir_change_threshold   = umu_cfg.get("direction_change_frames", 5)
        self.speed_jump_factor      = umu_cfg.get("speed_jump_factor", 3.0)
        self.back_forth_count       = umu_cfg.get("back_forth_count", 4)
        self.zone_repeat_count      = umu_cfg.get("zone_repeat_count", 3)
        self._cooldown: float       = config.get("events", {}).get("cooldown_seconds", 20.0)

        self._dir_history:   Dict[int, Deque]  = {}
        self._speed_history: Dict[int, Deque]  = {}
        self._zone_history:  Dict[int, Deque]  = {}
        self._last_event:    Dict              = {}

        logger.info(f"UnusualMovementDetector initialized | enabled={self.enabled}")

    def update(
        self,
        tracks: List[Track],
        camera_id: str,
        frame_number: int,
    ) -> List[AIEvent]:
        if not self.enabled:
            return []

        events = []
        now    = now_ts()
        seen   = {t.track_id for t in tracks}

        for track in tracks:
            if not track.is_confirmed:
                continue

            tid   = track.track_id
            speed = getattr(track, "_pixel_speed", 0.0)
            dirv  = track.direction.value
            zone  = track.current_zone

            # Init history
            if tid not in self._dir_history:
                self._dir_history[tid]   = deque(maxlen=self.history_frames)
                self._speed_history[tid] = deque(maxlen=self.history_frames)
                self._zone_history[tid]  = deque(maxlen=self.history_frames * 2)

            self._dir_history[tid].append(dirv)
            self._speed_history[tid].append(speed)
            if zone:
                self._zone_history[tid].append(zone)

            dh = self._dir_history[tid]
            sh = self._speed_history[tid]
            zh = self._zone_history[tid]

            detected_pattern = None
            explanation      = ""

            # ── Rule 1: Sudden direction change ──────────────────────────────
            if len(dh) >= self.dir_change_threshold + 1:
                recent = list(dh)[-self.dir_change_threshold:]
                current_dir = recent[-1]
                prev_dir    = recent[0]
                opposite    = DIRECTION_OPPOSITES.get(prev_dir)
                if (opposite and current_dir == opposite
                        and prev_dir not in ("UNKNOWN", "STATIONARY")):
                    detected_pattern = "SUDDEN_DIRECTION_CHANGE"
                    explanation = (
                        f"Sudden direction change: {prev_dir} → {current_dir} "
                        f"within {self.dir_change_threshold} frames."
                    )

            # ── Rule 2: Sudden speed change ──────────────────────────────────
            if not detected_pattern and len(sh) >= 5:
                recent_speeds = list(sh)[-5:]
                avg_prev = sum(recent_speeds[:-1]) / max(len(recent_speeds) - 1, 1)
                curr_spd = recent_speeds[-1]
                if avg_prev > 0.5 and curr_spd > avg_prev * self.speed_jump_factor:
                    detected_pattern = "SUDDEN_SPEED_CHANGE"
                    explanation = (
                        f"Sudden speed increase: {avg_prev:.1f} → {curr_spd:.1f} px/frame "
                        f"(factor: {curr_spd/avg_prev:.1f}x)."
                    )

            # ── Rule 3: Back and forth ───────────────────────────────────────
            if not detected_pattern and len(dh) >= self.back_forth_count * 2:
                recent = [d for d in list(dh)[-self.back_forth_count * 2:]
                          if d not in ("UNKNOWN", "STATIONARY")]
                reversals = sum(
                    1 for i in range(1, len(recent))
                    if DIRECTION_OPPOSITES.get(recent[i-1]) == recent[i]
                )
                if reversals >= self.back_forth_count:
                    detected_pattern = "BACK_AND_FORTH"
                    explanation = (
                        f"Repeated direction reversals detected: "
                        f"{reversals} reversals in {self.back_forth_count * 2} frames."
                    )

            # ── Rule 4: Stationary to fast ───────────────────────────────────
            if not detected_pattern and len(sh) >= 10:
                old_speeds = list(sh)[-10:-5]
                new_speed  = list(sh)[-1]
                avg_old    = sum(old_speeds) / max(len(old_speeds), 1)
                if avg_old < 1.5 and new_speed > 15.0:
                    detected_pattern = "STATIONARY_TO_FAST"
                    explanation = (
                        f"Object transitioned from near-stationary "
                        f"({avg_old:.1f} px/f) to fast ({new_speed:.1f} px/f)."
                    )

            # ── Rule 5: Repeated zone entry ──────────────────────────────────
            if not detected_pattern and len(zh) >= self.zone_repeat_count * 2:
                zone_counts = Counter(list(zh)[-self.zone_repeat_count * 4:])
                for z, cnt in zone_counts.items():
                    if cnt >= self.zone_repeat_count:
                        detected_pattern = "REPEATED_ZONE_ENTRY"
                        explanation = (
                            f"Object entered zone '{z}' {cnt} times recently."
                        )
                        break

            # ── Generate event if pattern detected ────────────────────────────
            if detected_pattern:
                key  = (tid, detected_pattern)
                last = self._last_event.get(key, 0.0)
                if (now - last) >= self._cooldown:
                    desc = (
                        f"{track.class_name.title()} (ID {track.track_id}): "
                        f"{explanation} "
                        f"NOTE: Unusual movement is an analytical observation only."
                    )
                    evt = AIEvent(
                        event_type=EventType.UNUSUAL_MOVEMENT_DETECTED,
                        camera_id=camera_id,
                        severity=Severity.MEDIUM,
                        risk_score=15,
                        track_id=track.track_id,
                        object_type=track.category,
                        object_class=track.class_name,
                        confidence=track.confidence,
                        bbox=list(track.bbox),
                        center=list(track.center),
                        zone_id=track.current_zone,
                        movement_state=track.movement_state.value,
                        direction=track.direction.value,
                        frame_number=frame_number,
                        description=desc,
                        model_name="RuleBased",
                    )
                    events.append(evt)
                    self._last_event[key] = now
                    logger.info(f"UNUSUAL | pattern={detected_pattern} | track={tid}")

        # Cleanup
        for tid in list(self._dir_history):
            if tid not in seen:
                self._dir_history.pop(tid, None)
                self._speed_history.pop(tid, None)
                self._zone_history.pop(tid, None)

        return events
