"""
src/evidence/evidence_manager.py
==================================
PURPOSE:
    Captures and saves evidence images when important events occur.

    For each HIGH/CRITICAL event (or any configured severity):
    1. Take the current frame
    2. Draw bounding box, track ID, event type, zone, timestamp
    3. Save to: data/evidence/{camera_id}/{date}/{event_id}.jpg

    Evidence images are stored for authorized human review.
    Do NOT alter the original CCTV recording.

HOW TO USE:
    from src.evidence.evidence_manager import EvidenceManager

    evidence = EvidenceManager(config)
    path = evidence.capture(frame, event, track=track)
    # path = "data/evidence/camera_001/2026-08-29/evt_000001.jpg"
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional
from datetime import datetime

from src.events.event import AIEvent
from src.events.event_types import Severity
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EvidenceManager:
    """
    Saves annotated evidence images for important events.

    Attributes:
        enabled:          Whether evidence capture is active
        base_dir:         Root directory for evidence storage
        min_severity:     Minimum severity to capture (default: MEDIUM)
        jpeg_quality:     JPEG compression quality (0-100)
    """

    # Minimum severity levels that trigger evidence capture
    CAPTURE_SEVERITIES = {Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL}

    # BGR colors for severity labels on evidence images
    SEVERITY_COLORS = {
        "INFO":     (200, 200, 200),
        "LOW":      (0, 200, 100),
        "MEDIUM":   (0, 165, 255),
        "HIGH":     (0, 0, 255),
        "CRITICAL": (0, 0, 200),
    }

    def __init__(self, config: dict):
        """
        Initialize from config.yaml evidence section.

        Args:
            config: Full config.yaml dictionary
        """
        ev_cfg = config.get("evidence", {})
        self.enabled: bool = ev_cfg.get("save_images", True)
        self.base_dir = Path(ev_cfg.get("base_dir", "data/evidence"))
        self.jpeg_quality: int = ev_cfg.get("jpeg_quality", 90)

        self._saved_count = 0
        logger.info(
            f"EvidenceManager initialized | "
            f"enabled={self.enabled} | dir={self.base_dir}"
        )

    def capture(
        self,
        frame: np.ndarray,
        event: AIEvent,
    ) -> Optional[str]:
        """
        Capture and save an annotated evidence image for an event.

        Args:
            frame: BGR image (current video frame)
            event: The AIEvent that triggered this capture

        Returns:
            Absolute path to saved image, or None if not saved
        """
        if not self.enabled:
            return None

        # Only capture for medium+ severity
        if event.severity not in self.CAPTURE_SEVERITIES:
            return None

        try:
            # ── Build save path ────────────────────────────────────────────
            date_str = datetime.now().strftime("%Y-%m-%d")
            save_dir = self.base_dir / event.camera_id / date_str
            save_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{event.event_id}.jpg"
            save_path = save_dir / filename

            # ── Annotate frame ─────────────────────────────────────────────
            annotated = frame.copy()
            self._draw_evidence_overlay(annotated, event)

            # ── Save ───────────────────────────────────────────────────────
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
            cv2.imwrite(str(save_path), annotated, encode_params)

            self._saved_count += 1
            rel_path = str(save_path)
            logger.info(f"Evidence saved: {rel_path}")
            return rel_path

        except Exception as e:
            logger.error(f"Failed to save evidence for {event.event_id}: {e}")
            return None

    def _draw_evidence_overlay(self, frame: np.ndarray, event: AIEvent) -> None:
        """
        Draw event information overlay on the evidence image.

        Args:
            frame: BGR image to annotate (in place)
            event: The AIEvent being evidenced
        """
        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        sev_str = event.severity.value if event.severity else "INFO"
        sev_color = self.SEVERITY_COLORS.get(sev_str, (255, 255, 255))

        # ── Draw bounding box if available ─────────────────────────────────
        if event.bbox and len(event.bbox) == 4:
            x1, y1, x2, y2 = event.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), sev_color, 3)

            if event.track_id is not None:
                cv2.putText(
                    frame, f"ID:{event.track_id}",
                    (x1, y2 + 20),
                    font, 0.6, sev_color, 2
                )

        # ── Top banner ─────────────────────────────────────────────────────
        banner_h = 90
        banner = frame.copy()
        cv2.rectangle(banner, (0, 0), (w, banner_h), (20, 20, 20), -1)
        cv2.addWeighted(banner, 0.85, frame, 0.15, 0, frame)

        # Severity badge
        badge_w = 120
        cv2.rectangle(frame, (0, 0), (badge_w, banner_h), sev_color, -1)
        cv2.putText(
            frame, sev_str,
            (8, 45),
            font, 0.75, (0, 0, 0), 2
        )

        # Event info text
        lines_text = [
            f"EVENT: {event.event_type.value}",
            f"Camera: {event.camera_id}  |  ID: {event.event_id}",
            f"Time: {event.timestamp}",
            f"Object: {event.object_class or event.object_type}  "
            f"Track:{event.track_id}  "
            f"Conf:{f'{event.confidence:.0%}' if event.confidence else 'N/A'}  "
            f"Zone:{event.zone_id or 'None'}",
        ]
        for i, line in enumerate(lines_text):
            cv2.putText(
                frame, line,
                (badge_w + 8, 20 + i * 18),
                font, 0.45, (220, 220, 220), 1
            )

        # ── Bottom description strip ───────────────────────────────────────
        desc_short = event.description[:100] if event.description else ""
        cv2.rectangle(frame, (0, h - 30), (w, h), (20, 20, 20), -1)
        cv2.putText(
            frame, desc_short,
            (8, h - 10),
            font, 0.38, (180, 180, 180), 1
        )

    @property
    def saved_count(self) -> int:
        return self._saved_count
