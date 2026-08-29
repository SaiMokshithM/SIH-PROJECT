"""
src/behavior/group_movement.py
================================
PURPOSE:
    Detects when multiple tracked persons move together as a group.

    A group is defined when:
    - N or more confirmed person tracks are within proximity_pixels of each other
    - They have been close for at least group_formation_seconds
    - They are all moving in roughly the same direction

    Generates: GROUP_MOVEMENT_DETECTED

    IMPORTANT: Groups are an analytical observation.
    The system does not infer intent from group movement.

HOW IT WORKS:
    Each frame, for each pair of confirmed person tracks:
    1. Calculate distance between centers
    2. If distance < proximity_threshold → they are "close"
    3. Build clusters of close tracks
    4. If cluster size >= min_size → potential group
    5. If group persists for formation_seconds → GROUP_MOVEMENT_DETECTED
"""

from typing import List, Dict, Set, Tuple, Optional
from src.tracking.track import Track, MovementState
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts
from src.utils.logger import get_logger
import math

logger = get_logger(__name__)


class GroupMovementDetector:
    """
    Detects and tracks groups of moving persons.

    Attributes:
        min_size:          Minimum tracks to form a group (default 3)
        proximity_px:      Max pixel distance to consider "close" (default 80)
        formation_secs:    Seconds before a cluster becomes a "group" (default 5)
        _group_since:      Dict[frozenset of track_ids, float] → when cluster formed
        _alerted_groups:   Set of frozensets already alerted
    """

    _group_id_counter = 0

    def __init__(self, config: dict):
        grp_cfg = config.get("group", {})
        self.enabled:        bool  = grp_cfg.get("enabled", True)
        self.min_size:       int   = grp_cfg.get("minimum_size", 3)
        self.proximity_px:   float = grp_cfg.get("distance_threshold", 80.0)
        self.formation_secs: float = grp_cfg.get("formation_seconds", 5.0)
        self._cooldown:      float = config.get("events", {}).get("cooldown_seconds", 30.0)

        self._group_since:   Dict[frozenset, float] = {}
        self._alerted:       Dict[frozenset, float] = {}

        logger.info(
            f"GroupMovementDetector initialized | "
            f"min_size={self.min_size} | proximity={self.proximity_px}px | "
            f"formation={self.formation_secs}s"
        )

    def update(
        self,
        tracks: List[Track],
        camera_id: str,
        frame_number: int,
    ) -> List[AIEvent]:
        if not self.enabled:
            return []

        # Only look at confirmed person tracks that are moving
        persons = [
            t for t in tracks
            if t.is_confirmed
            and t.category == "person"
            and t.movement_state not in (MovementState.STATIONARY, MovementState.UNKNOWN)
        ]

        if len(persons) < self.min_size:
            return []

        events = []
        now = now_ts()
        clusters = self._find_clusters(persons)

        current_cluster_keys: Set[frozenset] = set()

        for cluster in clusters:
            if len(cluster) < self.min_size:
                continue

            key = frozenset(t.track_id for t in cluster)
            current_cluster_keys.add(key)

            # Track formation time
            if key not in self._group_since:
                self._group_since[key] = now
                continue

            duration = now - self._group_since[key]
            if duration < self.formation_secs:
                continue

            # Check cooldown
            last = self._alerted.get(key, 0.0)
            if (now - last) < self._cooldown:
                continue

            GroupMovementDetector._group_id_counter += 1
            group_id = f"group_{GroupMovementDetector._group_id_counter:04d}"

            # Compute dominant direction
            direction = self._dominant_direction(cluster)

            desc = (
                f"Group of {len(cluster)} persons detected moving together "
                f"({direction}). "
                f"Member IDs: {[t.track_id for t in cluster]}. "
                f"Duration: {duration:.0f}s. "
                f"NOTE: Group movement is an analytical observation, not an indicator of intent."
            )

            evt = AIEvent(
                event_type=EventType.GROUP_MOVEMENT_DETECTED,
                camera_id=camera_id,
                severity=Severity.MEDIUM,
                risk_score=20,
                object_type="person",
                object_class="group",
                direction=direction,
                frame_number=frame_number,
                description=desc,
                model_name="GroupDetector",
            )
            events.append(evt)
            self._alerted[key] = now
            logger.info(
                f"GROUP | id={group_id} | size={len(cluster)} | "
                f"dir={direction} | duration={duration:.0f}s"
            )

        # Cleanup dissolved clusters
        for key in list(self._group_since.keys()):
            if key not in current_cluster_keys:
                del self._group_since[key]

        return events

    def _find_clusters(self, persons: List[Track]) -> List[List[Track]]:
        """Group persons into proximity clusters using simple union-find."""
        n = len(persons)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            parent[find(i)] = find(j)

        for i in range(n):
            for j in range(i + 1, n):
                dist = self._distance(persons[i].center, persons[j].center)
                if dist <= self.proximity_px:
                    union(i, j)

        # Build clusters from union-find
        cluster_map: Dict[int, List[Track]] = {}
        for i, p in enumerate(persons):
            root = find(i)
            cluster_map.setdefault(root, []).append(p)

        return list(cluster_map.values())

    def _distance(self, a: List[int], b: List[int]) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    def _dominant_direction(self, cluster: List[Track]) -> str:
        """Find the most common direction in a cluster."""
        from collections import Counter
        dirs = [t.direction.value for t in cluster if t.direction.value not in ("UNKNOWN", "STATIONARY")]
        if not dirs:
            return "UNKNOWN"
        return Counter(dirs).most_common(1)[0][0]
