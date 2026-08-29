"""
src/behavior/loitering.py
==========================
PURPOSE:
    Detects when a tracked object has been inside a zone
    for longer than the configured loitering threshold.

    Uses the zone entry timestamps already tracked by ZoneManager.
    Works for people, vehicles, and animals.

HOW IT WORKS:
    Every frame, for each confirmed track inside each zone:
    1. Ask ZoneManager: "how long has track X been in zone Y?"
    2. If duration >= threshold → generate LOITERING_DETECTED event
    3. Apply cooldown so we don't repeat the event every frame

    The loitering threshold is configurable:
    - Global default in config.yaml
    - Per-zone override in zones.yaml

DEDUPLICATION:
    Once a LOITERING_DETECTED event fires for (track, zone),
    we wait for:
      a) The track to leave the zone (reset timer)
      b) The cooldown period to pass (re-alert)

    This prevents spamming hundreds of identical events while
    someone stands still in a zone.

HOW TO USE:
    from src.behavior.loitering import LoiteringDetector

    loitering = LoiteringDetector(config, zone_manager)
    events = loitering.update(tracks, camera_id="camera_001", frame_number=500)
"""

from typing import List, Dict, Tuple, Optional, Set
from src.tracking.track import Track
from src.zones.zone_manager import ZoneManager
from src.zones.zone import ZoneType
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LoiteringDetector:
    """
    Detects prolonged presence (loitering) of tracked objects in zones.

    Attributes:
        zone_manager:       Reference to ZoneManager (for zone durations)
        default_threshold:  Default loitering time in seconds
        re_alert_seconds:   Time before re-alerting for continued loitering
        _alerted:           Set of (track_id, zone_id) already alerted
        _last_alert_time:   Dict of (track_id, zone_id) → timestamp of last alert
    """

    def __init__(self, config: dict, zone_manager: ZoneManager):
        """
        Initialize loitering detector.

        Args:
            config:       Full config.yaml dictionary
            zone_manager: Reference to the active ZoneManager instance

        Reads from config:
            loitering.enabled                  (default: True)
            loitering.default_threshold_seconds (default: 30)
            loitering.re_alert_seconds          (default: 60)
        """
        loiter_cfg = config.get("loitering", {})
        self.enabled: bool = loiter_cfg.get("enabled", True)
        self.default_threshold: float = loiter_cfg.get("default_threshold_seconds", 30.0)
        self.re_alert_seconds: float = loiter_cfg.get("re_alert_seconds", 60.0)

        self.zone_manager = zone_manager

        # (track_id, zone_id) → True if first loitering alert already fired
        self._alerted: Set[Tuple[int, str]] = set()

        # (track_id, zone_id) → timestamp of last alert (for re-alerting)
        self._last_alert_time: Dict[Tuple[int, str], float] = {}

        # Track which (track, zone) combos we know about
        # If a track leaves a zone, we remove it from _alerted
        self._known_in_zone: Dict[int, Set[str]] = {}

        logger.info(
            f"LoiteringDetector initialized | "
            f"threshold={self.default_threshold}s | "
            f"re_alert={self.re_alert_seconds}s"
        )

    def update(
        self,
        tracks: List[Track],
        camera_id: str,
        frame_number: int = 0,
    ) -> List[AIEvent]:
        """
        Check all confirmed tracks in all zones for loitering.

        Call this every frame AFTER ZoneManager.update().

        Args:
            tracks:       List of active Track objects (zone info already set)
            camera_id:    Camera identifier for events
            frame_number: Current frame number

        Returns:
            List of AIEvent objects for loitering detections this frame
        """
        if not self.enabled:
            return []

        events: List[AIEvent] = []
        now = now_ts()
        seen_track_ids = {t.track_id for t in tracks}

        for track in tracks:
            if not track.is_confirmed:
                continue

            tid = track.track_id

            # Get all zones this track is currently inside
            current_zones = self.zone_manager._track_zones.get(tid, set())

            # Detect loitering in each zone the track is in
            for zone_id in current_zones:
                zone_obj = self.zone_manager._get_zone(zone_id)
                if zone_obj is None:
                    continue

                # Get how long this track has been in this zone
                duration = self.zone_manager.get_zone_duration(tid, zone_id)

                # Get threshold: per-zone override or global default
                threshold = zone_obj.loitering_threshold_seconds or self.default_threshold

                key = (tid, zone_id)

                # ── Check if we should fire loitering alert ────────────────
                if duration >= threshold:
                    first_alert = key not in self._alerted
                    re_alert_due = (
                        key in self._last_alert_time and
                        (now - self._last_alert_time[key]) >= self.re_alert_seconds
                    )

                    if first_alert or re_alert_due:
                        event = self._make_loitering_event(
                            track, zone_obj, duration, camera_id, frame_number
                        )
                        if event:
                            events.append(event)
                            self._alerted.add(key)
                            self._last_alert_time[key] = now

                            logger.info(
                                f"LOITERING | track={tid} ({track.class_name}) "
                                f"| zone={zone_id} [{zone_obj.zone_type}] "
                                f"| duration={duration:.0f}s"
                            )

            # Track current zones for exit detection (reset loitering state)
            prev_zones = self._known_in_zone.get(tid, set())
            exited_zones = prev_zones - current_zones

            for zone_id in exited_zones:
                key = (tid, zone_id)
                self._alerted.discard(key)
                self._last_alert_time.pop(key, None)
                logger.debug(f"Loitering timer reset: track={tid} exited zone={zone_id}")

            self._known_in_zone[tid] = current_zones

        # Clean up state for deleted tracks
        for tid in list(self._known_in_zone.keys()):
            if tid not in seen_track_ids:
                del self._known_in_zone[tid]
                # Clean up alerts for this track
                self._alerted = {k for k in self._alerted if k[0] != tid}

        return events

    def _make_loitering_event(
        self,
        track: Track,
        zone,
        duration: float,
        camera_id: str,
        frame_number: int,
    ) -> Optional[AIEvent]:
        """
        Build the LOITERING_DETECTED event.

        Args:
            track:        The Track object
            zone:         The Zone object
            duration:     How long the track has been in the zone (seconds)
            camera_id:    Camera identifier
            frame_number: Current frame number

        Returns:
            AIEvent for loitering
        """
        # Severity escalates for restricted zones
        if zone.is_high_security:
            severity = Severity.CRITICAL
        elif zone.is_restricted:
            severity = Severity.HIGH
        else:
            severity = Severity.MEDIUM

        mins = int(duration // 60)
        secs = int(duration % 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        desc = (
            f"Prolonged presence detected. "
            f"{track.class_name.title()} (ID {track.track_id}) "
            f"has been in zone '{zone.name}' for {time_str}. "
            f"Movement: {track.movement_state.value}. "
            f"NOTE: Loitering is an analytical observation, not an indicator of intent."
        )

        return AIEvent(
            event_type=EventType.LOITERING_DETECTED,
            camera_id=camera_id,
            severity=severity,
            risk_score=self._compute_risk(zone, duration),
            track_id=track.track_id,
            object_type=track.category,
            object_class=track.class_name,
            confidence=track.confidence,
            bbox=list(track.bbox),
            center=list(track.center),
            zone_id=zone.zone_id,
            zone_name=zone.name,
            movement_state=track.movement_state.value,
            direction=track.direction.value,
            pixel_speed=getattr(track, "_pixel_speed", None),
            duration_seconds=duration,
            frame_number=frame_number,
            description=desc,
            model_name="YOLOv8",
        )

    def _compute_risk(self, zone, duration: float) -> int:
        """
        Compute a 0-100 operational risk score for loitering.

        Factors:
        - Base: zone type
        - Duration bonus: longer = higher score
        - Capped at 100

        NOTE: This is an operational priority score, NOT a threat probability.

        Args:
            zone:     Zone object
            duration: How long in zone (seconds)

        Returns:
            int: Risk score 0-100
        """
        base = 0
        if zone.is_high_security:
            base = 70
        elif zone.is_restricted:
            base = 50
        else:
            base = 20

        # Add time bonus: +1 for each 10 seconds beyond threshold
        threshold = zone.loitering_threshold_seconds or self.default_threshold
        extra_time = max(0, duration - threshold)
        time_bonus = min(20, int(extra_time / 10))

        return min(100, base + time_bonus)
