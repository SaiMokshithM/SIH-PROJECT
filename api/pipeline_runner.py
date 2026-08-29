"""
api/pipeline_runner.py
======================
Background thread that wraps the existing SIH-main AI pipeline.
Runs YOLO detection, tracking, zone analysis, risk engine in a loop.
Exposes shared PipelineState read by the FastAPI WebSocket server.

Architecture:
    Camera/Video/Image → Detector → Tracker → ZoneManager → RiskEngine
                                                              ↓
                                              PipelineState (thread-safe)
                                                              ↓
                                              FastAPI WebSocket → Browser
"""

import sys
import time
import threading
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import base64
import json
import uuid

# Ensure project root is on path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config_loader import load_config
from src.utils.time_utils import now_iso, now_ts
from src.detection.detector import Detector
from src.tracking.tracker import Tracker
from src.movement.movement_analyzer import MovementAnalyzer
from src.behavior.movement_events import MovementEventDetector
from src.behavior.loitering import LoiteringDetector
from src.behavior.night_detector import NightDetector
from src.behavior.group_movement import GroupMovementDetector
from src.behavior.unusual_movement import UnusualMovementDetector
from src.zones.zone_manager import ZoneManager
from src.zones.line_crossing import LineCrossingDetector
from src.faces.face_detector import FaceDetector
from src.anpr.anpr_module import ANPRModule
from src.weapons.weapon_detector import WeaponDetector
from src.events.risk_engine import RiskEngine
from src.camera_health.health_monitor import CameraHealthMonitor
from src.events.event_types import Severity

FONT = cv2.FONT_HERSHEY_SIMPLEX
SEV_COLOR = {
    "CRITICAL": (0, 0, 220),
    "HIGH":     (0, 60, 220),
    "MEDIUM":   (0, 130, 230),
    "LOW":      (50, 180, 50),
    "INFO":     (80, 80, 80),
}


@dataclass
class DetectionInfo:
    track_id: int
    class_name: str
    category: str
    confidence: float
    bbox: List[int]
    center: List[int]
    movement_state: str
    direction: str
    is_confirmed: bool
    current_zone: Optional[str]
    risk_score: int
    time_in_scene: float
    first_seen: str
    last_seen: str


@dataclass
class EventInfo:
    event_id: str
    event_type: str
    severity: str
    camera_id: str
    timestamp: str
    track_id: Optional[int]
    object_type: Optional[str]
    zone_id: Optional[str]
    zone_name: Optional[str]
    description: str
    risk_score: int


@dataclass
class PipelineState:
    """Shared state between the AI pipeline thread and FastAPI server."""
    lock: threading.Lock = field(default_factory=threading.Lock)

    # System
    running: bool = False
    camera_status: str = "offline"
    processing: bool = False
    fps: float = 0.0
    frame_number: int = 0
    last_update: str = ""
    model_name: str = "yolov8n.pt"
    camera_id: str = "camera_001"
    is_night: bool = False
    error_message: str = ""

    # Current frame as JPEG bytes (annotated)
    frame_jpeg: Optional[bytes] = None

    # Detections / tracks
    detections: List[DetectionInfo] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=lambda: {
        "person": 0, "vehicle": 0, "animal": 0, "total": 0, "tracked": 0
    })

    # Events (rolling 50)
    recent_events: List[EventInfo] = field(default_factory=list)
    event_count_session: int = 0

    # Risk
    risk_score: int = 0
    risk_level: str = "INFO"

    # Module status
    anpr_enabled: bool = False
    weapon_enabled: bool = False
    face_enabled: bool = True
    zones_loaded: int = 0

    # Image-mode result
    image_result: Optional[bytes] = None
    image_detections: List[dict] = field(default_factory=list)

    def to_ws_message(self) -> dict:
        """Serialize state to WebSocket JSON message."""
        with self.lock:
            return {
                "timestamp": self.last_update,
                "camera_id": self.camera_id,
                "fps": round(self.fps, 1),
                "model": self.model_name,
                "processing": self.processing,
                "camera_status": self.camera_status,
                "is_night": self.is_night,
                "risk_score": self.risk_score,
                "risk_level": self.risk_level,
                "counts": dict(self.counts),
                "detections": [
                    {
                        "track_id": d.track_id,
                        "class_name": d.class_name,
                        "category": d.category,
                        "confidence": round(d.confidence, 3),
                        "bbox": d.bbox,
                        "center": d.center,
                        "movement_state": d.movement_state,
                        "direction": d.direction,
                        "is_confirmed": d.is_confirmed,
                        "current_zone": d.current_zone,
                        "risk_score": d.risk_score,
                        "time_in_scene": round(d.time_in_scene, 1),
                        "first_seen": d.first_seen,
                        "last_seen": d.last_seen,
                    }
                    for d in self.detections
                ],
                "events": [
                    {
                        "event_id": e.event_id,
                        "event_type": e.event_type,
                        "severity": e.severity,
                        "camera_id": e.camera_id,
                        "timestamp": e.timestamp,
                        "track_id": e.track_id,
                        "object_type": e.object_type,
                        "zone_id": e.zone_id,
                        "zone_name": e.zone_name,
                        "description": e.description,
                        "risk_score": e.risk_score,
                    }
                    for e in self.recent_events[-20:]
                ],
                "module_status": {
                    "anpr": self.anpr_enabled,
                    "weapon": self.weapon_enabled,
                    "face": self.face_enabled,
                    "zones": self.zones_loaded,
                },
                "error": self.error_message,
            }


# Singleton state
state = PipelineState()


def draw_annotated_frame(frame: np.ndarray, tracks, track_risks: dict, zone_manager=None, line_crossing=None) -> np.ndarray:
    """Draw zones, virtual lines, bounding boxes and labels on frame using existing track data."""
    out = frame.copy()
    h, w = out.shape[:2]

    # Draw zones first (semi-transparent)
    if zone_manager is not None:
        zone_manager.draw_zones(out)
    if line_crossing is not None:
        line_crossing.draw_lines(out)

    for t in tracks:
        if not t.is_confirmed:
            continue
        x1, y1, x2, y2 = t.bbox
        color = t.color
        risk = track_risks.get(t.track_id, 0)

        # High-risk red ring
        if risk >= 60:
            cv2.rectangle(out, (x1-2, y1-2), (x2+2, y2+2), (0, 0, 255), 2)

        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        z_tag = "HIGH" if (t.current_zone and "high" in t.current_zone) else \
                ("MED" if (t.current_zone and "med" in t.current_zone) else "LOW")
        label = f"{t.class_name.upper()} #{t.track_id} {t.confidence:.0%} | {z_tag}: {risk}%"

        (lw, lh), base = cv2.getTextSize(label, FONT, 0.44, 1)
        ly = max(y1, lh + 6)
        cv2.rectangle(out, (x1, ly-lh-4), (x1+lw+4, ly+base-2), color, -1)
        cv2.putText(out, label, (x1+2, ly-3), FONT, 0.44, (0, 0, 0), 1)

        # Trajectory trail
        traj = list(t.trajectory)[-20:]
        for i in range(1, len(traj)):
            alpha = i / len(traj)
            tc = tuple(int(c * alpha) for c in color)
            cv2.line(out, tuple(traj[i-1]), tuple(traj[i]), tc, 1)
        cv2.circle(out, tuple(t.center), 3, color, -1)

    return out


def draw_hud_overlay(
    frame: np.ndarray,
    fps: float,
    frame_num: int,
    camera_id: str,
    counts: dict,
    is_night: bool,
    risk_score: int,
    risk_level: str,
) -> np.ndarray:
    """Draw HUD overlay with real stats."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 75), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    ts = datetime.now().strftime("%H:%M:%S")
    night_tag = "  NIGHT" if is_night else ""
    cv2.putText(frame, f"BORDER AI  [LIVE]{night_tag}  {ts}", (8, 18), FONT, 0.52, (0, 200, 255), 1)
    cv2.putText(frame,
        f"Cam:{camera_id}  FPS:{fps:4.1f}  Frame:{frame_num:05d}",
        (8, 36), FONT, 0.40, (200, 200, 200), 1)
    p = counts.get("person", 0)
    v = counts.get("vehicle", 0)
    a = counts.get("animal", 0)
    cv2.putText(frame, f"P:{p}  V:{v}  A:{a}", (8, 54), FONT, 0.44, (100, 255, 100), 1)

    risk_color = (0, 220, 100) if risk_level == "INFO" else \
                 (50, 180, 50)  if risk_level == "LOW" else \
                 (0, 130, 230)  if risk_level == "MEDIUM" else \
                 (0, 60, 220)   if risk_level == "HIGH" else (0, 0, 220)
    cv2.putText(frame, f"RISK:{risk_score} [{risk_level}]", (8, 70), FONT, 0.38, risk_color, 1)
    return frame


def frame_to_jpeg(frame: np.ndarray, quality: int = 75) -> bytes:
    """Encode OpenCV frame to JPEG bytes."""
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


class PipelineRunner:
    """
    Wraps the existing AI modules in a background thread.
    The FastAPI server reads from `state` to serve the dashboard.
    """

    def __init__(self, config: dict):
        self.config = config
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        model_cfg = config.get("model", {})
        with state.lock:
            state.model_name = model_cfg.get("path", "yolov8n.pt")
            state.anpr_enabled = config.get("anpr", {}).get("enabled", False)
            state.weapon_enabled = config.get("weapon_detection", {}).get("enabled", False)
            state.face_enabled = config.get("face_detection", {}).get("enabled", True)

        # Load all AI modules once
        self.detector = Detector(model_cfg)
        self.tracker = Tracker(config.get("tracking", {}))
        self.movement_ana = MovementAnalyzer(config.get("movement", {}))
        self.move_events = MovementEventDetector(config)
        self.zone_manager = ZoneManager(config)
        self.loitering_det = LoiteringDetector(config, self.zone_manager)
        self.night_det = NightDetector(config)
        self.group_det = GroupMovementDetector(config)
        self.unusual_det = UnusualMovementDetector(config)
        self.line_crossing = LineCrossingDetector(config)
        self.face_det = FaceDetector(config)
        self.anpr = ANPRModule(config)
        self.weapon_det = WeaponDetector(config)
        self.risk_engine = RiskEngine(config)
        self.health_monitor = CameraHealthMonitor(config)

        # Load zones/lines
        n_zones = self.zone_manager.load_zones("config/zones.yaml")
        n_lines = self.line_crossing.load_lines("config/cameras.yaml")
        with state.lock:
            state.zones_loaded = n_zones

        print(f"[Pipeline] Zones:{n_zones} Lines:{n_lines}")

    def load_model(self) -> bool:
        ok = self.detector.load()
        return ok

    def start(self, source, camera_id: str = "camera_001"):
        """Start live camera/video loop in background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(source, camera_id),
            daemon=True,
        )
        with state.lock:
            state.camera_id = camera_id
            state.running = True
        self._thread.start()

    def stop(self):
        """Signal the loop to stop."""
        self._stop_event.set()
        with state.lock:
            state.running = False
            state.camera_status = "offline"
            state.processing = False

    def process_image(self, img_array: np.ndarray, camera_id: str = "image_upload") -> dict:
        """
        Run YOLO + ANPR + Weapon Detection on a single uploaded image.
        Returns annotated JPEG bytes + detection list + adds events to Live Feed.
        """
        detections = self.detector.detect(img_array, frame_number=0, camera_id=camera_id)
        out = img_array.copy()
        h, w = img_array.shape[:2]

        result_dets = []
        counts = {"person": 0, "vehicle": 0, "animal": 0, "weapon": 0, "plate": 0, "total": 0}
        new_events = []
        now = now_iso()

        # 1. Annotate YOLO detections
        for d in detections:
            x1, y1, x2, y2 = d.bbox
            color = d.color
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            label = f"{d.class_name.upper()} {d.confidence:.0%}"
            (lw, lh), base = cv2.getTextSize(label, FONT, 0.5, 1)
            ly = max(y1, lh + 6)
            cv2.rectangle(out, (x1, ly-lh-4), (x1+lw+4, ly+base-2), color, -1)
            cv2.putText(out, label, (x1+2, ly-3), FONT, 0.5, (0, 0, 0), 1)

            if d.category in counts:
                counts[d.category] += 1

            result_dets.append({
                "class_name": d.class_name,
                "category": d.category,
                "confidence": round(d.confidence, 3),
                "bbox": d.bbox,
                "center": d.center,
            })

            # Check if this is a weapon
            if d.category == "weapon" or d.class_name in ("knife", "scissors", "gun", "pistol", "rifle"):
                counts["weapon"] += 1
                evt = EventInfo(
                    event_id=f"evt_{uuid.uuid4().hex[:8]}",
                    event_type="POTENTIAL_WEAPON_DETECTED",
                    severity="CRITICAL",
                    camera_id=camera_id,
                    timestamp=now,
                    track_id=None,
                    object_type="weapon",
                    zone_id=None,
                    zone_name="Image Upload",
                    description=f"CRITICAL: Weapon detected ({d.class_name.upper()}) with {d.confidence:.0%} confidence.",
                    risk_score=90,
                )
                new_events.append(evt)

        # 2. Run ANPR on vehicles and entire frame
        vehicle_dets = [d for d in detections if d.category == "vehicle"]
        found_plates = set()

        # Check vehicle crops
        for vd in vehicle_dets:
            vx1, vy1, vx2, vy2 = vd.bbox
            v_crop = img_array[max(0, vy1):min(h, vy2), max(0, vx1):min(w, vx2)]
            if v_crop.size > 0:
                plate = self.anpr._find_and_read_plate(v_crop, (max(0, vx1), max(0, vy1)))
                if plate and plate.plate_text not in found_plates:
                    found_plates.add(plate.plate_text)
                    px1, py1, px2, py2 = plate.plate_bbox
                    cv2.rectangle(out, (px1, py1), (px2, py2), (255, 255, 0), 2)
                    p_label = f"PLATE: {plate.plate_text}"
                    cv2.putText(out, p_label, (px1, max(15, py1 - 5)), FONT, 0.55, (255, 255, 0), 2)
                    counts["plate"] += 1
                    result_dets.append({
                        "class_name": f"License Plate: {plate.plate_text}",
                        "category": "plate",
                        "confidence": round(plate.plate_confidence, 2),
                        "bbox": [px1, py1, px2, py2],
                        "center": [(px1 + px2) // 2, (py1 + py2) // 2],
                    })
                    evt = EventInfo(
                        event_id=f"evt_{uuid.uuid4().hex[:8]}",
                        event_type="LICENSE_PLATE_DETECTED",
                        severity="INFO",
                        camera_id=camera_id,
                        timestamp=now,
                        track_id=None,
                        object_type="vehicle",
                        zone_id=None,
                        zone_name="Image Upload",
                        description=f"License plate '{plate.plate_text}' identified (Conf: {plate.plate_confidence:.0%}).",
                        risk_score=20,
                    )
                    new_events.append(evt)

        # Fallback whole-image scan if vehicles didn't yield a plate or no vehicle box
        if counts["plate"] == 0:
            plate = self.anpr._find_and_read_plate(img_array, (0, 0))
            if plate and plate.plate_text:
                px1, py1, px2, py2 = plate.plate_bbox
                cv2.rectangle(out, (px1, py1), (px2, py2), (255, 255, 0), 2)
                p_label = f"PLATE: {plate.plate_text}"
                cv2.putText(out, p_label, (px1, max(15, py1 - 5)), FONT, 0.55, (255, 255, 0), 2)
                counts["plate"] += 1
                result_dets.append({
                    "class_name": f"License Plate: {plate.plate_text}",
                    "category": "plate",
                    "confidence": round(plate.plate_confidence, 2),
                    "bbox": [px1, py1, px2, py2],
                    "center": [(px1 + px2) // 2, (py1 + py2) // 2],
                })
                evt = EventInfo(
                    event_id=f"evt_{uuid.uuid4().hex[:8]}",
                    event_type="LICENSE_PLATE_DETECTED",
                    severity="INFO",
                    camera_id=camera_id,
                    timestamp=now,
                    track_id=None,
                    object_type="vehicle",
                    zone_id=None,
                    zone_name="Image Upload",
                    description=f"License plate '{plate.plate_text}' identified (Conf: {plate.plate_confidence:.0%}).",
                    risk_score=20,
                )
                new_events.append(evt)

        # 3. Dedicated Firearm / Weapon Model Detection
        raw_weapons = self.weapon_det.detect_raw(img_array)
        for w_name, w_conf, w_box in raw_weapons:
            wx1, wy1, wx2, wy2 = w_box
            cv2.rectangle(out, (wx1, wy1), (wx2, wy2), (0, 0, 255), 3)
            w_label = f"WEAPON: {w_name.upper()} {w_conf:.0%}"
            (wlw, wlh), wbase = cv2.getTextSize(w_label, FONT, 0.55, 2)
            wly = max(wy1, wlh + 8)
            cv2.rectangle(out, (wx1, wly-wlh-6), (wx1+wlw+6, wly+wbase-2), (0, 0, 255), -1)
            cv2.putText(out, w_label, (wx1+3, wly-3), FONT, 0.55, (255, 255, 255), 2)
            counts["weapon"] += 1
            result_dets.append({
                "class_name": f"Weapon: {w_name}",
                "category": "weapon",
                "confidence": round(w_conf, 3),
                "bbox": [wx1, wy1, wx2, wy2],
                "center": [(wx1 + wx2) // 2, (wy1 + wy2) // 2],
            })
            evt = EventInfo(
                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type="POTENTIAL_WEAPON_DETECTED",
                severity="CRITICAL",
                camera_id=camera_id,
                timestamp=now,
                track_id=None,
                object_type="weapon",
                zone_id=None,
                zone_name="Image Upload",
                description=f"CRITICAL: Firearm / Weapon detected ({w_name.upper()}) with {w_conf:.0%} confidence.",
                risk_score=90,
            )
            new_events.append(evt)

        counts["total"] = len(result_dets)

        # Push events to shared state
        if new_events:
            with state.lock:
                state.recent_events.extend(new_events)
                state.event_count_session += len(new_events)
                if counts["weapon"] > 0:
                    state.risk_score = 90
                    state.risk_level = "CRITICAL"

        jpeg = frame_to_jpeg(out, quality=85)
        return {"jpeg": jpeg, "detections": result_dets, "counts": counts, "events": [e.__dict__ for e in new_events]}

    def _run_loop(self, source, camera_id: str):
        """Main AI loop — runs in background thread."""
        from src.video.video_source import VideoSource

        fps_count = 0
        fps_timer = now_ts()
        fps_val = 0.0
        frame_num = 0
        track_risks: Dict[int, int] = {}

        video = VideoSource(source, camera_id=camera_id)
        if not video.open():
            with state.lock:
                state.camera_status = "offline"
                state.error_message = f"Cannot open source: {source}"
            print(f"[Pipeline] Cannot open source: {source}")
            return

        with state.lock:
            state.camera_status = "online"
            state.processing = True
            state.error_message = ""

        print(f"[Pipeline] Started | source={source} | camera={camera_id}")

        skip = max(1, self.config.get("performance", {}).get("process_every_n_frames", 1))

        while not self._stop_event.is_set():
            ok, frame = video.read()

            # Camera health
            health_events = self.health_monitor.update(camera_id, frame if ok else None, ok)
            if not ok:
                if video.is_file:
                    video.rewind()
                    continue
                with state.lock:
                    state.camera_status = "offline"
                time.sleep(0.1)
                continue

            frame_num += 1
            if frame_num % skip != 0:
                continue

            # Night mode
            is_night = self.night_det.is_night_time(frame)

            # Detection
            detections = self.detector.detect(frame, frame_number=frame_num, camera_id=camera_id)
            fh, fw = frame.shape[:2]

            # Supplement close-up webcam faces as person detections if YOLO body box missed
            if self.face_det.enabled:
                try:
                    raw_faces = self.face_det._run_detection(frame)
                    for face in raw_faces:
                        fx1, fy1, fx2, fy2 = face.bbox
                        fcx = (fx1 + fx2) // 2
                        fcy = (fy1 + fy2) // 2
                        
                        # Check if any existing person detection covers this face
                        covered = False
                        for d in detections:
                            if d.category == "person":
                                dx1, dy1, dx2, dy2 = d.bbox
                                if dx1 <= fcx <= dx2 and dy1 <= fcy <= dy2:
                                    covered = True
                                    break
                        if not covered:
                            pw = fx2 - fx1
                            ph = fy2 - fy1
                            px1 = max(0, fx1 - int(pw * 0.35))
                            py1 = max(0, fy1 - int(ph * 0.2))
                            px2 = min(fw, fx2 + int(pw * 0.35))
                            py2 = min(fh, fy2 + int(ph * 1.6))
                            from src.detection.detection_result import DetectionResult
                            detections.append(DetectionResult(
                                class_name="person",
                                class_id=0,
                                confidence=face.confidence or 0.85,
                                bbox=[px1, py1, px2, py2],
                                center=[(px1 + px2) // 2, (py1 + py2) // 2],
                                category="person",
                                frame_number=frame_num,
                                camera_id=camera_id,
                                color=(0, 255, 0),
                            ))
                except Exception:
                    pass

            # Tracking
            tracks = self.tracker.update(detections, camera_id=camera_id)

            # Movement
            for t in tracks:
                self.movement_ana.analyze(t)

            # Events
            all_events = []
            all_events.extend(self.move_events.update(tracks, camera_id, frame_num))
            fh, fw = frame.shape[:2]

            # Zones & Lines
            zone_events = self.zone_manager.update(tracks, camera_id, frame_num, frame_w=fw, frame_h=fh)
            all_events.extend(zone_events)
            line_events = self.line_crossing.update(tracks, camera_id, frame_num)
            all_events.extend(line_events)

            # Night detection
            is_night = self.night_det.is_night_time(frame)
            night_evts = self.night_det.update(tracks, camera_id, frame_num, is_night)
            all_events.extend(night_evts)

            all_events.extend(self.loitering_det.update(tracks, camera_id, frame_num))
            all_events.extend(self.group_det.update(tracks, camera_id, frame_num))
            all_events.extend(self.unusual_det.update(tracks, camera_id, frame_num))

            # Face
            if self.face_det.enabled:
                p_tracks = [t for t in tracks if t.category == "person" and t.is_confirmed]
                _, face_evts = self.face_det.detect(frame, p_tracks, camera_id, frame_num)
                all_events.extend(face_evts)

            # ANPR
            if self.anpr.enabled:
                v_tracks = [t for t in tracks if t.category == "vehicle" and t.is_confirmed]
                if v_tracks:
                    _, anpr_evts = self.anpr.process(frame, v_tracks, camera_id, frame_num)
                    all_events.extend(anpr_evts)

            # Weapon
            if self.weapon_det.enabled:
                p_tracks = [t for t in tracks if t.category == "person"]
                _, wpn_evts = self.weapon_det.detect(frame, p_tracks, camera_id, frame_num)
                all_events.extend(wpn_evts)

            # Risk evaluation - strictly partitioned 33% Low, 33% Med, 33% High
            self.risk_engine.ingest_events(all_events)
            track_risks = {}
            primary_risk = 0
            primary_level = "INFO"

            confirmed_tracks = [t for t in tracks if t.is_confirmed]
            # Sort descending by bbox area: largest (closest foreground subject) is index 0
            confirmed_tracks.sort(key=lambda t: (t.bbox[2]-t.bbox[0]) * (t.bbox[3]-t.bbox[1]), reverse=True)

            for i, t in enumerate(confirmed_tracks):
                cx, _ = t.center
                norm_cx = cx / max(1, fw)

                # Strict 33.3% Partitioning:
                if norm_cx >= 0.666:     # Right 33.3% (66.6% to 100%) -> High Risk
                    t.current_zone = "zone_high"
                    score = 90
                    level_str = "CRITICAL"
                elif norm_cx < 0.333:    # Left 33.3% (0% to 33.3%) -> Low Risk
                    t.current_zone = "zone_low"
                    score = 20
                    level_str = "LOW"
                else:                    # Middle 33.3% (33.3% to 66.6%) -> Medium Risk
                    t.current_zone = "zone_med"
                    score = 50
                    level_str = "MEDIUM"

                track_risks[t.track_id] = score

                if i == 0:
                    primary_risk = score
                    primary_level = level_str

            # FPS
            fps_count += 1
            elapsed = now_ts() - fps_timer
            if elapsed >= 1.0:
                fps_val = fps_count / elapsed
                fps_count = 0
                fps_timer = now_ts()

            # Build annotated frame with zones & lines
            annotated = draw_annotated_frame(frame, tracks, track_risks, self.zone_manager, self.line_crossing)
            annotated = draw_hud_overlay(
                annotated, fps_val, frame_num, camera_id,
                {}, is_night, primary_risk, primary_level
            )

            # Counts
            counts = {"person": 0, "vehicle": 0, "animal": 0, "total": 0, "tracked": 0}
            for t in tracks:
                if t.is_confirmed and t.category in counts:
                    counts[t.category] += 1
                    counts["tracked"] += 1
            counts["total"] = counts["person"] + counts["vehicle"] + counts["animal"]

            # Build detection infos
            det_infos = []
            for t in tracks:
                det_infos.append(DetectionInfo(
                    track_id=t.track_id,
                    class_name=t.class_name,
                    category=t.category,
                    confidence=t.confidence,
                    bbox=list(t.bbox),
                    center=list(t.center),
                    movement_state=t.movement_state.value,
                    direction=t.direction.value,
                    is_confirmed=t.is_confirmed,
                    current_zone=t.current_zone,
                    risk_score=track_risks.get(t.track_id, 0),
                    time_in_scene=t.time_in_scene,
                    first_seen=datetime.fromtimestamp(t.first_seen).strftime("%H:%M:%S"),
                    last_seen=datetime.fromtimestamp(t.last_seen).strftime("%H:%M:%S"),
                ))

            # Event infos
            new_event_infos = []
            for evt in all_events:
                sev_val = evt.severity.value if evt.severity else "INFO"
                new_event_infos.append(EventInfo(
                    event_id=evt.event_id,
                    event_type=evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type),
                    severity=sev_val,
                    camera_id=evt.camera_id,
                    timestamp=evt.timestamp,
                    track_id=evt.track_id,
                    object_type=evt.object_type,
                    zone_id=evt.zone_id,
                    zone_name=evt.zone_name,
                    description=evt.description,
                    risk_score=evt.risk_score,
                ))

            jpeg = frame_to_jpeg(annotated, quality=60)

            # Update shared state
            with state.lock:
                state.fps = fps_val
                state.frame_number = frame_num
                state.is_night = is_night
                state.camera_status = "online"
                state.processing = True
                state.last_update = now_iso()
                state.risk_score = primary_risk
                state.risk_level = primary_level
                state.counts = counts
                state.detections = det_infos
                state.frame_jpeg = jpeg
                state.recent_events.extend(new_event_infos)
                state.event_count_session += len(new_event_infos)
                if len(state.recent_events) > 200:
                    state.recent_events = state.recent_events[-200:]

        video.release()
        with state.lock:
            state.camera_status = "offline"
            state.processing = False
        print("[Pipeline] Stopped.")
