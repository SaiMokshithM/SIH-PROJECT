"""
src/tracking/tracker.py
========================
PURPOSE:
    Multi-object tracker using IoU-based matching.

    This is the "memory" of the system. Every frame it:
    1. Receives new detections from the detector
    2. Tries to match each detection to an existing track
    3. Updates matched tracks with new position
    4. Creates new tracks for unmatched detections
    5. Marks unmatched tracks as LOST
    6. Deletes tracks missing for too long

CONCEPTS FOR BEGINNERS:
    IoU (Intersection over Union):
        Measures how much two bounding boxes overlap.
        0.0 = boxes don't overlap at all
        1.0 = boxes are identical

        Example:
        Frame 100: Person detected at [100, 50, 200, 300]
        Frame 101: Person detected at [105, 52, 205, 302]
        IoU ≈ 0.95 → Same person! Update the existing track.

    Hungarian Algorithm / Greedy matching:
        When multiple detections and tracks exist, we find the
        BEST OVERALL assignment of detections to tracks.
        We use greedy IoU matching which is simple and fast.

TRACKING LIFECYCLE:
    New detection → TENTATIVE track (ID assigned)
        ↓ (seen min_hits frames)
    CONFIRMED track
        ↓ (not seen for 1 frame)
    LOST track
        ↓ (not seen for max_age frames)
    DELETED track (removed)
"""

from typing import List, Dict, Optional, Tuple
import numpy as np

from src.tracking.track import Track, TrackState
from src.detection.detection_result import DetectionResult
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── IoU Utilities ─────────────────────────────────────────────────────────────

def compute_iou(box_a: List[int], box_b: List[int]) -> float:
    """
    Compute Intersection over Union between two bounding boxes.

    Args:
        box_a: [x1, y1, x2, y2]
        box_b: [x1, y1, x2, y2]

    Returns:
        float: IoU score between 0.0 and 1.0

    Example:
        iou = compute_iou([0,0,100,100], [50,50,150,150])
        # → 0.142 (small overlap)
    """
    # Find intersection rectangle
    ix1 = max(box_a[0], box_b[0])
    iy1 = max(box_a[1], box_b[1])
    ix2 = min(box_a[2], box_b[2])
    iy2 = min(box_a[3], box_b[3])

    # Intersection area (0 if boxes don't overlap)
    inter_w = max(0, ix2 - ix1)
    inter_h = max(0, iy2 - iy1)
    intersection = inter_w * inter_h

    if intersection == 0:
        return 0.0

    # Union area
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - intersection

    if union <= 0:
        return 0.0

    return intersection / union


def compute_iou_matrix(
    tracks: List[Track],
    detections: List[DetectionResult],
) -> np.ndarray:
    """
    Compute a matrix of IoU scores between all tracks and all detections.

    Returns:
        numpy array of shape (num_tracks, num_detections)
        iou_matrix[i][j] = IoU between track i and detection j
    """
    n_tracks = len(tracks)
    n_dets = len(detections)

    if n_tracks == 0 or n_dets == 0:
        return np.zeros((n_tracks, n_dets))

    matrix = np.zeros((n_tracks, n_dets))
    for i, track in enumerate(tracks):
        for j, det in enumerate(detections):
            # Only match objects of the same class
            if track.class_id == det.class_id:
                matrix[i][j] = compute_iou(track.bbox, det.bbox)

    return matrix


def greedy_match(
    iou_matrix: np.ndarray,
    iou_threshold: float,
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """
    Greedy IoU matching: match tracks to detections.

    Iteratively picks the highest IoU pair, assigns it, then removes
    that track and detection from consideration.

    Args:
        iou_matrix:    (n_tracks x n_dets) matrix of IoU scores
        iou_threshold: Minimum IoU to accept a match

    Returns:
        matches:         List of (track_index, detection_index) pairs
        unmatched_tracks: Track indices with no matched detection
        unmatched_dets:   Detection indices with no matched track
    """
    matches = []
    n_tracks, n_dets = iou_matrix.shape

    if n_tracks == 0 or n_dets == 0:
        return [], list(range(n_tracks)), list(range(n_dets))

    # Work on a copy
    matrix = iou_matrix.copy()
    assigned_tracks = set()
    assigned_dets = set()

    # Keep picking the best match until none are above threshold
    while True:
        if matrix.max() < iou_threshold:
            break

        # Find the best IoU pair
        flat_idx = np.argmax(matrix)
        t_idx = flat_idx // n_dets
        d_idx = flat_idx % n_dets

        matches.append((t_idx, d_idx))
        assigned_tracks.add(t_idx)
        assigned_dets.add(d_idx)

        # Zero out this track's row and detection's column
        matrix[t_idx, :] = 0
        matrix[:, d_idx] = 0

    unmatched_tracks = [i for i in range(n_tracks) if i not in assigned_tracks]
    unmatched_dets   = [j for j in range(n_dets)   if j not in assigned_dets]

    return matches, unmatched_tracks, unmatched_dets


# ── Multi-Object Tracker ──────────────────────────────────────────────────────

class Tracker:
    """
    IoU-based multi-object tracker.

    Maintains a dictionary of active Track objects.
    Each frame, it matches new detections to existing tracks.

    Attributes:
        config:          Tracking config dict from config.yaml
        tracks:          Dict of track_id → Track for all active tracks
        iou_threshold:   Minimum IoU to match detection to track
        max_age:         Frames before a LOST track is deleted
        min_hits:        Frames needed before track is CONFIRMED
        trajectory_len:  How many past positions to remember
    """

    def __init__(self, config: dict):
        """
        Initialize the tracker.

        Args:
            config: The 'tracking' section from config.yaml

        Expected config keys:
            enabled:          bool
            history_length:   int  (trajectory length)
            max_age:          int  (frames before deleting lost tracks)
            min_hits:         int  (frames before confirming a track)
            iou_threshold:    float (min overlap to match)
        """
        self.config = config
        self.enabled: bool = config.get("enabled", True)
        self.iou_threshold: float = config.get("iou_threshold", 0.3)
        self.max_age: int = config.get("max_age", 30)
        self.min_hits: int = config.get("min_hits", 3)
        self.trajectory_len: int = config.get("history_length", 30)

        # Active tracks: track_id → Track
        self.tracks: Dict[int, Track] = {}

        # Statistics
        self._total_tracks_created: int = 0
        self._frame_count: int = 0

        logger.info(
            f"Tracker initialized | "
            f"iou={self.iou_threshold} | "
            f"max_age={self.max_age} | "
            f"min_hits={self.min_hits}"
        )

    def update(
        self,
        detections: List[DetectionResult],
        camera_id: str = "camera_001",
    ) -> List[Track]:
        """
        Process one frame's detections and update all tracks.

        This is the main method called every frame.

        Args:
            detections: List of DetectionResult from the detector
            camera_id:  Camera identifier for new tracks

        Returns:
            List of currently CONFIRMED and TENTATIVE tracks
            (only tracks visible to the user — not DELETED ones)

        Example:
            tracks = tracker.update(detections, camera_id="camera_001")
            for track in tracks:
                print(f"ID {track.track_id}: {track.class_name} at {track.center}")
        """
        self._frame_count += 1

        if not self.enabled:
            return []

        # ── Get active (non-deleted) tracks ────────────────────────
        active_tracks = [
            t for t in self.tracks.values()
            if t.state != TrackState.DELETED
        ]

        # ── Match detections to tracks using IoU ───────────────────
        iou_matrix = compute_iou_matrix(active_tracks, detections)
        matches, unmatched_track_idxs, unmatched_det_idxs = greedy_match(
            iou_matrix, self.iou_threshold
        )

        # ── Update matched tracks ──────────────────────────────────
        for t_idx, d_idx in matches:
            track = active_tracks[t_idx]
            det = detections[d_idx]
            track.update(
                bbox=det.bbox,
                center=det.center,
                confidence=det.confidence,
                color=det.color,
            )
            # Promote to CONFIRMED if enough hits
            if (track.is_tentative and track.hit_streak >= self.min_hits):
                track.confirm()
                logger.debug(
                    f"Track {track.track_id} CONFIRMED | "
                    f"class={track.class_name} | hits={track.hit_streak}"
                )

        # ── Mark unmatched tracks as missed ───────────────────────
        for t_idx in unmatched_track_idxs:
            track = active_tracks[t_idx]
            track.mark_missed()

            if track.frames_since_update >= self.max_age:
                track.mark_deleted()
                logger.debug(
                    f"Track {track.track_id} DELETED | "
                    f"class={track.class_name} | "
                    f"lived={track.time_in_scene:.1f}s"
                )
            elif track.frames_since_update >= 1 and track.state != TrackState.TENTATIVE:
                track.mark_lost()

        # ── Create new tracks for unmatched detections ─────────────
        for d_idx in unmatched_det_idxs:
            det = detections[d_idx]
            new_track = Track(
                class_name=det.class_name,
                class_id=det.class_id,
                category=det.category,
                bbox=list(det.bbox),
                center=list(det.center),
                confidence=det.confidence,
                camera_id=camera_id,
                color=det.color,
                max_trajectory_length=self.trajectory_len,
            )
            self.tracks[new_track.track_id] = new_track
            self._total_tracks_created += 1
            logger.debug(
                f"New track #{new_track.track_id} | "
                f"class={new_track.class_name} | "
                f"conf={new_track.confidence:.2f}"
            )

        # ── Remove deleted tracks from memory ──────────────────────
        deleted_ids = [
            tid for tid, t in self.tracks.items()
            if t.state == TrackState.DELETED
        ]
        for tid in deleted_ids:
            del self.tracks[tid]

        # ── Return visible tracks (confirmed + tentative) ──────────
        visible = [
            t for t in self.tracks.values()
            if t.state in (TrackState.CONFIRMED, TrackState.TENTATIVE)
        ]

        if visible:
            logger.debug(
                f"Frame {self._frame_count}: "
                f"{len(visible)} active tracks | "
                f"{len(matches)} matched | "
                f"{len(unmatched_det_idxs)} new"
            )

        return visible

    def get_track(self, track_id: int) -> Optional[Track]:
        """Get a track by its ID. Returns None if not found."""
        return self.tracks.get(track_id)

    def get_confirmed_tracks(self) -> List[Track]:
        """Return only CONFIRMED tracks."""
        return [t for t in self.tracks.values() if t.is_confirmed]

    def get_all_tracks(self) -> List[Track]:
        """Return all non-deleted tracks."""
        return [
            t for t in self.tracks.values()
            if t.state != TrackState.DELETED
        ]

    def count_by_class(self) -> Dict[str, int]:
        """Count confirmed tracks grouped by class name."""
        counts: Dict[str, int] = {}
        for t in self.get_confirmed_tracks():
            counts[t.class_name] = counts.get(t.class_name, 0) + 1
        return counts

    def count_by_category(self) -> Dict[str, int]:
        """Count confirmed tracks grouped by category."""
        counts: Dict[str, int] = {}
        for t in self.get_confirmed_tracks():
            counts[t.category] = counts.get(t.category, 0) + 1
        return counts

    def reset(self) -> None:
        """Clear all tracks (e.g. when switching cameras)."""
        self.tracks.clear()
        logger.info("Tracker reset — all tracks cleared.")

    def get_stats(self) -> dict:
        """Return tracker statistics."""
        return {
            "total_tracks_created": self._total_tracks_created,
            "active_tracks":        len(self.get_all_tracks()),
            "confirmed_tracks":     len(self.get_confirmed_tracks()),
            "frames_processed":     self._frame_count,
        }
