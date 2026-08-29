"""
src/camera_health/health_monitor.py
=====================================
PURPOSE:
    Monitors camera stream health and generates alerts when:
    - Camera goes offline (no frames received)
    - Stream has errors
    - Frames appear frozen (identical frames for N seconds)
    - Camera recovers after an outage

    Events:
        CAMERA_OFFLINE
        CAMERA_STREAM_ERROR
        CAMERA_FRAME_FREEZE
        CAMERA_RECOVERED

HOW IT WORKS:
    Every frame, call update() with success=True/False.
    The monitor tracks:
    - Last successful frame timestamp
    - Frame content hash (to detect frozen streams)
    - Current health state
"""

import hashlib
import numpy as np
from typing import Dict, Optional, List
from src.events.event import AIEvent
from src.events.event_types import EventType, Severity
from src.utils.time_utils import now_ts, now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CameraState:
    HEALTHY  = "HEALTHY"
    OFFLINE  = "OFFLINE"
    FROZEN   = "FROZEN"
    DEGRADED = "DEGRADED"


class CameraHealthMonitor:
    """
    Monitors health of one or more camera streams.

    Attributes:
        timeout_secs:    Seconds without frames before OFFLINE event
        freeze_secs:     Seconds of identical frames before FREEZE event
        check_interval:  Minimum seconds between repeated health events
    """

    def __init__(self, config: dict):
        cam_cfg = config.get("camera_health", {})
        self.enabled:        bool  = cam_cfg.get("enabled", True)
        self.timeout_secs:   float = cam_cfg.get("timeout_seconds", 10.0)
        self.freeze_secs:    float = cam_cfg.get("freeze_check_interval", 5.0)
        self.event_cooldown: float = config.get("events", {}).get("cooldown_seconds", 30.0)

        # Per-camera state: camera_id → dict
        self._camera_state: Dict[str, dict] = {}

        logger.info(
            f"CameraHealthMonitor initialized | "
            f"timeout={self.timeout_secs}s | freeze={self.freeze_secs}s"
        )

    def _init_camera(self, camera_id: str) -> None:
        if camera_id not in self._camera_state:
            self._camera_state[camera_id] = {
                "state":          CameraState.HEALTHY,
                "last_frame_ts":  now_ts(),
                "last_frame_hash": None,
                "freeze_since":   None,
                "last_event_ts":  {},
                "frames_received": 0,
                "errors":         0,
            }

    def update(
        self,
        camera_id: str,
        frame: Optional[np.ndarray],
        success: bool,
    ) -> List[AIEvent]:
        """
        Update camera health state and generate events if needed.

        Args:
            camera_id: Camera identifier
            frame:     The frame (None if read failed)
            success:   Whether frame was read successfully

        Returns:
            List of health events (usually empty)
        """
        if not self.enabled:
            return []

        self._init_camera(camera_id)
        state   = self._camera_state[camera_id]
        events  = []
        now     = now_ts()
        was_ok  = state["state"] == CameraState.HEALTHY

        if success and frame is not None:
            state["frames_received"] += 1
            old_ts    = state["last_frame_ts"]
            state["last_frame_ts"] = now

            # ── Freeze detection ─────────────────────────────────────────
            frame_hash = self._hash_frame(frame)
            if frame_hash == state["last_frame_hash"]:
                if state["freeze_since"] is None:
                    state["freeze_since"] = now
                elif (now - state["freeze_since"]) >= self.freeze_secs:
                    if state["state"] != CameraState.FROZEN:
                        state["state"] = CameraState.FROZEN
                        evt = self._make_event(
                            EventType.CAMERA_FRAME_FREEZE, camera_id,
                            f"Camera '{camera_id}' stream appears frozen — identical frames for "
                            f"{now - state['freeze_since']:.0f}s."
                        )
                        if evt:
                            events.append(evt)
            else:
                state["freeze_since"]   = None
                state["last_frame_hash"] = frame_hash

                # ── Recovery ──────────────────────────────────────────────
                if not was_ok:
                    state["state"] = CameraState.HEALTHY
                    evt = self._make_event(
                        EventType.CAMERA_RECOVERED, camera_id,
                        f"Camera '{camera_id}' recovered — frames received again."
                    )
                    if evt:
                        events.append(evt)
                    logger.info(f"Camera recovered: {camera_id}")

        else:
            # Frame read failed
            state["errors"] += 1
            time_since_last = now - state["last_frame_ts"]

            if time_since_last >= self.timeout_secs and state["state"] != CameraState.OFFLINE:
                state["state"] = CameraState.OFFLINE
                evt = self._make_event(
                    EventType.CAMERA_OFFLINE, camera_id,
                    f"Camera '{camera_id}' offline — no frames for {time_since_last:.0f}s."
                )
                if evt:
                    events.append(evt)
                    logger.warning(f"Camera offline: {camera_id}")

        return events

    def _make_event(
        self,
        event_type: EventType,
        camera_id: str,
        description: str,
    ) -> Optional[AIEvent]:
        """Create health event with cooldown check."""
        state = self._camera_state.get(camera_id, {})
        last_events = state.get("last_event_ts", {})
        now = now_ts()

        key = event_type.value
        last = last_events.get(key, 0.0)
        if (now - last) < self.event_cooldown:
            return None

        last_events[key] = now

        return AIEvent(
            event_type=event_type,
            camera_id=camera_id,
            severity=Severity.HIGH if event_type != EventType.CAMERA_RECOVERED else Severity.INFO,
            description=description,
            model_name="CameraHealthMonitor",
        )

    def _hash_frame(self, frame: np.ndarray) -> str:
        """Compute a quick perceptual hash of a frame to detect freeze."""
        # Downsample to 16x16 grayscale for speed
        small = frame[::frame.shape[0]//16 or 1, ::frame.shape[1]//16 or 1, 0]
        return hashlib.md5(small.tobytes()).hexdigest()

    def get_status(self) -> Dict[str, str]:
        """Return current health state for all cameras."""
        return {cam_id: s["state"] for cam_id, s in self._camera_state.items()}
