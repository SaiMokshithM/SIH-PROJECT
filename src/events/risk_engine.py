"""
src/events/risk_engine.py
==========================
PURPOSE:
    Combines multiple event signals to compute an operational
    risk score (0–100) and severity level for each track.

    CRITICAL DISCLAIMER:
    This score is an OPERATIONAL PRIORITIZATION TOOL.
    It is NOT a probability that a person is dangerous.
    It is NOT a legal assessment.
    It must ALWAYS be reviewed by an authorized human operator.

    Scoring signals (configurable):
        RESTRICTED_ZONE_INTRUSION   +50
        HIGH_SECURITY_ZONE_INTRUSION +80
        VIRTUAL_FENCE_CROSSING      +30
        NIGHT_ZONE_INTRUSION        +20
        LOITERING_DETECTED          +15
        UNUSUAL_MOVEMENT_DETECTED   +10
        POTENTIAL_WEAPON_DETECTED   +80
        GROUP_MOVEMENT_DETECTED     +10
        FAST_MOVEMENT_DETECTED      +5
        Night time bonus            +10

    Severity thresholds:
        0–19    → INFO
        20–39   → LOW
        40–59   → MEDIUM
        60–79   → HIGH
        80–100  → CRITICAL

HOW TO USE:
    risk_engine = RiskEngine(config)
    score, severity = risk_engine.evaluate(events_for_this_track)
"""

from typing import List, Dict, Optional, Tuple
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default signal weights — all configurable via config.yaml
DEFAULT_WEIGHTS: Dict[str, int] = {
    EventType.HIGH_SECURITY_ZONE_INTRUSION.value: 80,
    EventType.POTENTIAL_WEAPON_DETECTED.value:    80,
    EventType.RESTRICTED_ZONE_INTRUSION.value:    50,
    EventType.VIRTUAL_FENCE_CROSSING.value:       30,
    EventType.NIGHT_ZONE_INTRUSION.value:         25,
    EventType.NIGHT_MOVEMENT_DETECTED.value:      10,
    EventType.LOITERING_DETECTED.value:           15,
    EventType.UNUSUAL_MOVEMENT_DETECTED.value:    10,
    EventType.GROUP_MOVEMENT_DETECTED.value:      10,
    EventType.FAST_MOVEMENT_DETECTED.value:        5,
    EventType.STATIONARY_OBJECT.value:             3,
    EventType.SLOW_MOVEMENT_DETECTED.value:        2,
}


class RiskEngine:
    """
    Evaluates accumulated events to compute operational risk score per track.

    Maintains a rolling window of recent events per (track, camera).
    Scores are decayed over time (old events contribute less).

    Attributes:
        weights:       Signal → score contribution
        decay_secs:    Seconds before event contribution decays to 0
        _track_events: Dict[(track_id, camera_id), List[(event, timestamp)]]
    """

    def __init__(self, config: dict):
        risk_cfg = config.get("risk_engine", {})
        self.enabled:     bool  = risk_cfg.get("enabled", True)
        self.decay_secs:  float = risk_cfg.get("decay_seconds", 120.0)
        self.max_score:   int   = risk_cfg.get("max_score", 100)

        # Load weights from config or use defaults
        user_weights = risk_cfg.get("weights", {})
        self.weights = {**DEFAULT_WEIGHTS, **user_weights}

        # (track_id, camera_id) → list of (AIEvent, float timestamp)
        self._track_events: Dict[Tuple, List] = {}

        logger.info(
            f"RiskEngine initialized | "
            f"decay={self.decay_secs}s | max_score={self.max_score}"
        )

    def ingest_events(self, events: List[AIEvent]) -> None:
        """
        Feed new events into the risk engine.

        Args:
            events: List of AIEvent objects from this frame
        """
        if not self.enabled:
            return

        now = now_ts()
        for evt in events:
            key = (evt.track_id or -1, evt.camera_id)
            self._track_events.setdefault(key, []).append((evt, now))

    def evaluate(
        self,
        track_id: int,
        camera_id: str,
        is_night: bool = False,
    ) -> Tuple[int, Severity]:
        """
        Compute current risk score for a track.

        Args:
            track_id:  Track ID (-1 for unassociated)
            camera_id: Camera ID
            is_night:  Whether night mode is active (adds bonus)

        Returns:
            (risk_score: 0–100, severity: Severity enum)
        """
        if not self.enabled:
            return 0, Severity.INFO

        key = (track_id, camera_id)
        now = now_ts()
        events = self._track_events.get(key, [])

        # Remove expired events
        events = [(e, t) for e, t in events if (now - t) < self.decay_secs]
        self._track_events[key] = events

        raw_score = 0
        for evt, t in events:
            weight   = self.weights.get(evt.event_type.value, 0)
            age_frac = 1.0 - min(1.0, (now - t) / self.decay_secs)
            raw_score += int(weight * age_frac)

        if is_night:
            raw_score += 10

        score    = min(self.max_score, raw_score)
        severity = self._score_to_severity(score)
        return score, severity

    def get_top_threats(self, camera_id: str, n: int = 5) -> List[dict]:
        """
        Return the N highest-risk tracks for a camera.

        Args:
            camera_id: Camera to query
            n:         Number of top tracks to return

        Returns:
            List of dicts: {track_id, risk_score, severity}
        """
        now     = now_ts()
        results = []
        for (tid, cam), events in self._track_events.items():
            if cam != camera_id:
                continue
            score, severity = self.evaluate(tid, cam)
            if score > 0:
                results.append({"track_id": tid, "risk_score": score, "severity": severity.value})

        return sorted(results, key=lambda x: x["risk_score"], reverse=True)[:n]

    def _score_to_severity(self, score: int) -> Severity:
        if score >= 80: return Severity.CRITICAL
        if score >= 60: return Severity.HIGH
        if score >= 40: return Severity.MEDIUM
        if score >= 20: return Severity.LOW
        return Severity.INFO
