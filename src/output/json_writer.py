"""
src/output/json_writer.py
==========================
PURPOSE:
    Writes AI events and detections to JSON Lines files.

    JSON Lines (.jsonl) format:
    - One JSON object per line
    - Easy to stream, append and parse
    - Compatible with any backend (Spring Boot, Python, JavaScript)

OUTPUT FILES:
    data/output/events.jsonl     ← All AI events
    data/output/detections.jsonl ← Per-frame detection records
    data/output/tracks.jsonl     ← Per-frame track state records

HOW TO USE:
    from src.output.json_writer import JSONWriter

    writer = JSONWriter("data/output")
    writer.write_event(event)
    writer.write_detection(detection_dict)
    writer.write_track(track_dict)
"""

import json
from pathlib import Path
from typing import Optional
from src.events.event import AIEvent
from src.utils.logger import get_logger
from src.utils.time_utils import now_iso

logger = get_logger(__name__)


class _NumpyEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles numpy scalar types produced by OpenCV/NumPy.

    OpenCV returns int32, float32, int64 etc. — standard json.dumps() can't
    serialize these, causing 'Object of type int32 is not JSON serializable'.
    This encoder converts them to standard Python ints/floats transparently.
    """
    def default(self, obj):
        import numpy as np
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class JSONWriter:
    """
    Appends events and detections to JSON Lines files.

    Thread-safe for single-process use (one camera at a time).
    For multi-camera concurrent writing, use separate writer instances.

    Attributes:
        output_dir:         Base directory for output files
        events_path:        Path to events.jsonl
        detections_path:    Path to detections.jsonl
        tracks_path:        Path to tracks.jsonl
    """

    def __init__(self, output_dir: str = "data/output"):
        """
        Initialize JSON writer and create output directory.

        Args:
            output_dir: Directory where .jsonl files will be written
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.events_path     = self.output_dir / "events.jsonl"
        self.detections_path = self.output_dir / "detections.jsonl"
        self.tracks_path     = self.output_dir / "tracks.jsonl"

        # Counters for logging
        self._events_written     = 0
        self._detections_written = 0
        self._tracks_written     = 0

        logger.info(f"JSONWriter initialized | output_dir={self.output_dir}")

    def write_event(self, event: AIEvent) -> bool:
        """
        Append an event to events.jsonl.

        Args:
            event: AIEvent object to serialize

        Returns:
            True if written successfully, False on error
        """
        try:
            record = event.to_dict()
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, cls=_NumpyEncoder) + "\n")
            self._events_written += 1
            logger.debug(f"Event written: {event.event_id} ({event.event_type.value})")
            return True
        except Exception as e:
            logger.error(f"Failed to write event {getattr(event, 'event_id', '?')}: {e}")
            return False

    def write_detection(self, detection_dict: dict) -> bool:
        """
        Append a detection record to detections.jsonl.

        Args:
            detection_dict: Dictionary from DetectionResult.to_dict()
                            plus any extra fields (timestamp, etc.)

        Returns:
            True if written successfully
        """
        try:
            with open(self.detections_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(detection_dict, ensure_ascii=False, cls=_NumpyEncoder) + "\n")
            self._detections_written += 1
            return True
        except Exception as e:
            logger.error(f"Failed to write detection: {e}")
            return False

    def write_track(self, track_dict: dict) -> bool:
        """
        Append a track state record to tracks.jsonl.

        Args:
            track_dict: Dictionary from Track.to_dict()

        Returns:
            True if written successfully
        """
        try:
            with open(self.tracks_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(track_dict, ensure_ascii=False, cls=_NumpyEncoder) + "\n")
            self._tracks_written += 1
            return True
        except Exception as e:
            logger.error(f"Failed to write track: {e}")
            return False

    def get_stats(self) -> dict:
        """Return write statistics."""
        return {
            "events_written":     self._events_written,
            "detections_written": self._detections_written,
            "tracks_written":     self._tracks_written,
            "output_dir":         str(self.output_dir),
        }
