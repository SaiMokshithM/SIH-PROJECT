"""
src/zones/zone_manager.py
==========================
PURPOSE:
    Loads all zone configurations and checks every tracked object
    against every zone each frame.

    Detects zone transitions:
        OUTSIDE → INSIDE  →  ZONE_ENTRY event
        INSIDE  → OUTSIDE →  ZONE_EXIT event

    For RESTRICTED zones:
        OUTSIDE → INSIDE  →  RESTRICTED_ZONE_INTRUSION event

    Implements deduplication:
        Only ONE ZONE_ENTRY event per (track, zone) pair.
        Only ONE ZONE_EXIT event when object leaves.
        No repeated intrusion events every frame.

    Also tracks how long each object has been in each zone —
    used later for loitering detection.

HOW TO USE:
    from src.zones.zone_manager import ZoneManager

    zone_manager = ZoneManager(config)
    zone_manager.load_zones("config/zones.yaml")

    events = zone_manager.update(tracks, camera_id="camera_001", frame_number=100)
    for event in events:
        print(event)
"""

from typing import List, Dict, Set, Optional, Tuple
from src.zones.zone import Zone, ZoneType
from src.tracking.track import Track
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts, now_iso
from src.utils.logger import get_logger
import yaml
from pathlib import Path

logger = get_logger(__name__)


class ZoneManager:
    """
    Manages all configured zones and detects zone crossing events.

    Attributes:
        zones:          List of Zone objects loaded from zones.yaml
        config:         Full config dict for thresholds
        _track_zones:   Dict[track_id, Set[zone_id]] — which zones each track is currently in
        _zone_entry_time: Dict[(track_id, zone_id), float] — when track entered the zone
        _cooldown_secs: Seconds between same event for same (track, zone)
        _last_event:    Dict[(track_id, zone_id, event_type), float] — dedup timestamps
    """

    def __init__(self, config: dict):
        """
        Initialize zone manager.

        Args:
            config: Full config.yaml dictionary
        """
        self.config = config
        self.zones: List[Zone] = []

        # Track → Set of zone IDs the track is currently inside
        self._track_zones: Dict[int, Set[str]] = {}

        # (track_id, zone_id) → timestamp when track entered that zone
        self._zone_entry_time: Dict[Tuple[int, str], float] = {}

        # Cooldown to prevent duplicate entry events
        self._cooldown_secs: float = config.get("events", {}).get("cooldown_seconds", 10.0)

        # (track_id, zone_id, event_type_value) → last event timestamp
        self._last_event: Dict[Tuple, float] = {}

        logger.info("ZoneManager initialized")

    def load_zones(self, zones_file: str = "config/zones.yaml") -> int:
        """
        Load zone definitions from YAML file.

        Args:
            zones_file: Path to zones.yaml

        Returns:
            Number of zones loaded
        """
        path = Path(zones_file)
        if not path.exists():
            logger.warning(f"Zones file not found: {zones_file} — no zones will be active")
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            raw_zones = data.get("zones", []) if data else []
            self.zones = []

            for z in raw_zones:
                if not z.get("enabled", True):
                    continue

                # Parse polygon — supports [[x,y], ...] or [[x, y], ...] YAML formats
                polygon = z.get("polygon", [])
                if not polygon or len(polygon) < 3:
                    logger.warning(f"Zone {z.get('id')} has fewer than 3 polygon points — skipped")
                    continue

                zone = Zone(
                    zone_id=z["id"],
                    name=z.get("name", z["id"]),
                    zone_type=z.get("type", ZoneType.MONITORING),
                    polygon=polygon,
                    enabled=z.get("enabled", True),
                    camera_id=z.get("camera_id", None),
                    loitering_threshold_seconds=z.get("loitering_threshold_seconds", None),
                )
                self.zones.append(zone)
                logger.info(
                    f"Zone loaded: [{zone.zone_id}] {zone.name!r} "
                    f"| type={zone.zone_type} | points={len(zone.polygon)}"
                )

            logger.info(f"Total zones loaded: {len(self.zones)}")
            return len(self.zones)

        except Exception as e:
            logger.error(f"Failed to load zones from {zones_file}: {e}")
            return 0

    def update(
        self,
        tracks: List[Track],
        camera_id: str,
        frame_number: int = 0,
        frame_w: int = 640,
        frame_h: int = 480,
    ) -> List[AIEvent]:
        """
        Check all confirmed tracks against all zones.
        """
        if not self.zones:
            return []

        events: List[AIEvent] = []
        now = now_ts()

        # Filter zones for this camera (or zones with no camera restriction)
        active_zones = [
            z for z in self.zones
            if z.enabled and (z.camera_id is None or z.camera_id == camera_id)
        ]

        seen_track_ids = {t.track_id for t in tracks}

        for track in tracks:
            if not track.is_confirmed:
                continue  # Only monitor confirmed tracks

            tid = track.track_id

            # Current zones this track is in
            current_zones: Set[str] = set()

            for zone in active_zones:
                if zone.contains_track(track, frame_w, frame_h):
                    current_zones.add(zone.zone_id)

                    # ── ENTRY detection ────────────────────────────────────
                    prev_zones = self._track_zones.get(tid, set())
                    if zone.zone_id not in prev_zones:
                        # Track just entered this zone
                        entry_key = (tid, zone.zone_id)
                        self._zone_entry_time[entry_key] = now

                        entry_events = self._on_zone_entry(
                            track, zone, camera_id, frame_number, now
                        )
                        events.extend(entry_events)

                        # Update track zone fields
                        track.previous_zone = track.current_zone
                        track.current_zone = zone.zone_id

            # ── EXIT detection ─────────────────────────────────────────────
            prev_zones = self._track_zones.get(tid, set())
            exited_zones = prev_zones - current_zones

            for zone_id in exited_zones:
                zone_obj = self._get_zone(zone_id)
                if zone_obj:
                    exit_events = self._on_zone_exit(
                        track, zone_obj, camera_id, frame_number, now
                    )
                    events.extend(exit_events)

                    # Clean up entry time
                    self._zone_entry_time.pop((tid, zone_id), None)

                    # Update track zone
                    track.previous_zone = zone_id
                    if not current_zones:
                        track.current_zone = None

            # Save current zone membership for next frame
            self._track_zones[tid] = current_zones

            # Update track's current_zone to the "most important" active zone
            if current_zones:
                # Prefer restricted zones in the label
                for z in active_zones:
                    if z.zone_id in current_zones and z.is_restricted:
                        track.current_zone = z.zone_id
                        break
                else:
                    track.current_zone = next(iter(current_zones))
            else:
                track.current_zone = None

        # ── Cleanup: remove zone state for deleted tracks ──────────────────
        for tid in list(self._track_zones.keys()):
            if tid not in seen_track_ids:
                del self._track_zones[tid]

        return events

    def get_zone_duration(self, track_id: int, zone_id: str) -> float:
        """
        How many seconds a track has been inside a specific zone.

        Args:
            track_id: Track integer ID
            zone_id:  Zone string ID

        Returns:
            float: Seconds in zone, or 0.0 if not in zone
        """
        key = (track_id, zone_id)
        entry_time = self._zone_entry_time.get(key)
        if entry_time is None:
            return 0.0
        return now_ts() - entry_time

    def get_zone_counts(self, camera_id: str = None) -> Dict[str, int]:
        """
        Count confirmed tracks currently inside each zone.

        Args:
            camera_id: Optional filter by camera

        Returns:
            Dict[zone_id, count]
        """
        counts: Dict[str, int] = {}
        for zone in self.zones:
            zone_tracks = sum(
                1 for zones in self._track_zones.values()
                if zone.zone_id in zones
            )
            counts[zone.zone_id] = zone_tracks
        return counts

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _on_zone_entry(
        self,
        track: Track,
        zone: Zone,
        camera_id: str,
        frame_number: int,
        now: float,
    ) -> List[AIEvent]:
        """Generate events when a track enters a zone."""
        events = []

        logger.info(
            f"ZONE ENTRY | track={track.track_id} ({track.class_name}) "
            f"→ zone={zone.zone_id} [{zone.zone_type}]"
        )

        # ── Basic ZONE_ENTRY for all zone types ────────────────────────────
        if self._can_fire(track.track_id, zone.zone_id, EventType.ZONE_ENTRY, now):
            event_type = EventType.ZONE_ENTRY
            severity = Severity.LOW
            evt_risk = 15

            # Choose event type based on zone type and object category
            if zone.is_high_security:
                event_type = EventType.HIGH_SECURITY_ZONE_INTRUSION
                severity = Severity.CRITICAL
                evt_risk = 90
            elif zone.is_restricted:
                event_type = EventType.RESTRICTED_ZONE_INTRUSION
                severity = Severity.HIGH
                evt_risk = 80
            elif zone.zone_type == ZoneType.MONITORING:
                event_type = EventType.ZONE_ENTRY
                severity = Severity.MEDIUM
                evt_risk = 50
            elif track.category == "animal":
                event_type = EventType.ANIMAL_ZONE_ENTRY
                severity = Severity.LOW
                evt_risk = 10

            desc = (
                f"{track.class_name.title()} (ID {track.track_id}) "
                f"entered {zone.name}."
            )
            if zone.is_restricted:
                desc += " Restricted area alert."

            evt = AIEvent(
                event_type=event_type,
                camera_id=camera_id,
                severity=severity,
                track_id=track.track_id,
                object_type=track.category,
                object_class=track.class_name,
                confidence=track.confidence,
                bbox=list(track.bbox),
                center=list(track.center),
                zone_id=zone.zone_id,
                zone_name=zone.name,
                risk_score=evt_risk,
                movement_state=track.movement_state.value,
                direction=track.direction.value,
                pixel_speed=getattr(track, "_pixel_speed", None),
                frame_number=frame_number,
                description=desc,
                model_name="YOLOv8",
            )
            events.append(evt)
            self._record_fire(track.track_id, zone.zone_id, EventType.ZONE_ENTRY, now)

        return events

    def _on_zone_exit(
        self,
        track: Track,
        zone: Zone,
        camera_id: str,
        frame_number: int,
        now: float,
    ) -> List[AIEvent]:
        """Generate events when a track exits a zone."""
        events = []

        duration = self.get_zone_duration(track.track_id, zone.zone_id)
        logger.info(
            f"ZONE EXIT | track={track.track_id} ({track.class_name}) "
            f"← zone={zone.zone_id} | was_inside={duration:.1f}s"
        )

        if zone.zone_type == ZoneType.SAFE:
            return events  # Don't generate exit events for safe zones

        event_type = EventType.ZONE_EXIT
        if track.category == "animal":
            event_type = EventType.ANIMAL_ZONE_EXIT

        evt = AIEvent(
            event_type=event_type,
            camera_id=camera_id,
            severity=Severity.INFO,
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
            duration_seconds=duration,
            frame_number=frame_number,
            description=(
                f"{track.class_name.title()} (ID {track.track_id}) "
                f"exited zone '{zone.name}' after {duration:.0f}s."
            ),
            model_name="YOLOv8",
        )
        events.append(evt)
        return events

    def _get_zone(self, zone_id: str) -> Optional[Zone]:
        """Look up a zone by ID."""
        for z in self.zones:
            if z.zone_id == zone_id:
                return z
        return None

    def _can_fire(
        self, track_id: int, zone_id: str, event_type: EventType, now: float
    ) -> bool:
        """Check if the cooldown has passed for a (track, zone, event) combo."""
        key = (track_id, zone_id, event_type.value)
        last = self._last_event.get(key, 0.0)
        return (now - last) >= self._cooldown_secs

    def _record_fire(
        self, track_id: int, zone_id: str, event_type: EventType, now: float
    ) -> None:
        """Record that an event just fired."""
        key = (track_id, zone_id, event_type.value)
        self._last_event[key] = now

    def draw_zones(self, frame, scale: float = 1.0) -> None:
        """
        Draw all zones on the frame as colored semi-transparent polygons.

        Args:
            frame: BGR image to draw on (modified in place)
            scale: Scale factor if frame was resized for display
        """
        import cv2
        import numpy as np

        fh, fw = frame.shape[:2]

        for zone in self.zones:
            if not zone.enabled:
                continue

            scaled_poly = zone.get_scaled_polygon(fw, fh)
            if not scaled_poly:
                continue

            pts = np.array(scaled_poly, dtype=np.int32)

            # ── Semi-transparent fill ──────────────────────────────────────
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], zone.color)
            cv2.addWeighted(overlay, zone.alpha, frame, 1 - zone.alpha, 0, frame)

            # ── Solid border ───────────────────────────────────────────────
            cv2.polylines(frame, [pts], isClosed=True, color=zone.color, thickness=2)

            # ── Zone label ─────────────────────────────────────────────────
            if len(pts) > 0:
                lx = int(pts[:, 0].min()) + 8
                ly = int(pts[:, 1].min()) + 24
                ly = max(ly, 28)
                
                tag = "HIGH RISK" if zone.is_restricted else ("MED RISK" if zone.zone_type == "MONITORING" else "LOW RISK")
                label = f"[{tag}] {zone.name}"
                (lw, lh), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
                cv2.rectangle(frame, (lx - 3, ly - lh - 4), (lx + lw + 4, ly + 3), (0, 0, 0), -1)
                cv2.rectangle(frame, (lx - 3, ly - lh - 4), (lx + lw + 4, ly + 3), zone.color, 1)
                cv2.putText(
                    frame, label,
                    (lx, ly - 1),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44,
                    zone.color, 1, cv2.LINE_AA
                )
