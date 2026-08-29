"""
src/main.py — Border AI Analytics Engine  v3.0.0 COMPLETE
============================================================
ALL MODULES ACTIVE:
    Detection     → Person / Vehicle / Animal (YOLOv8 COCO)
    Tracking      → IoU multi-object tracker with trajectory
    Movement      → Speed + Direction analysis (8 directions)
    Move Events   → STATIONARY / SLOW / FAST events
    Zones         → Polygon zone entry/exit/intrusion
    Loitering     → Prolonged presence detection
    Night Mode    → Time or brightness-based night detection
    Line Crossing → Virtual fence crossing detection
    Group Move    → Group formation detection
    Unusual Move  → 5 pattern-based unusual movement rules
    Face Detect   → Face detection (NO identification)
    ANPR          → License plate OCR (optional, needs easyocr)
    Weapon Detect → Plug-in weapon detector (needs specialized model)
    Risk Engine   → Decaying risk score per track
    Camera Health → Offline + freeze monitoring
    Evidence      → Auto-screenshot on HIGH/CRITICAL events
    JSON Output   → events.jsonl / detections.jsonl / tracks.jsonl

HOW TO RUN:
    python src/main.py --source webcam
    python src/main.py --source data/test_videos/test.mp4
    python src/main.py --camera camera_001
    python src/main.py --source webcam --confidence 0.35

KEYBOARD CONTROLS:
    Q / ESC = Quit
    S       = Save snapshot
    P       = Pause / Resume
    N       = Toggle night mode ON/OFF for testing
    F       = Toggle face detection overlay
    +/-     = Raise/lower confidence threshold
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import cv2
import numpy as np

from src.utils.logger import setup_logging, get_logger
from src.utils.config_loader import load_config, load_cameras
from src.utils.time_utils import now_iso, now_ts, date_folder_name
from src.detection.detector import Detector
from src.tracking.tracker import Tracker
from src.tracking.track import Track
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
from src.evidence.evidence_manager import EvidenceManager
from src.output.json_writer import JSONWriter
from src.events.event_types import Severity

logger = get_logger(__name__)

FONT       = cv2.FONT_HERSHEY_SIMPLEX
BOX_THICK  = 2

# BGR color per severity level
SEV_COLOR = {
    Severity.CRITICAL.value: (0,   0, 220),
    Severity.HIGH.value:     (0,  60, 220),
    Severity.MEDIUM.value:   (0, 130, 230),
    Severity.LOW.value:      (50, 180,  50),
    Severity.INFO.value:     (80,  80,  80),
}


# ─────────────────────────────────────────────────────────────
#  Drawing
# ─────────────────────────────────────────────────────────────

def draw_track(frame: np.ndarray, track: Track, risk_score: int = 0) -> None:
    color      = track.color
    draw_color = color if track.is_confirmed else tuple(c // 2 for c in color)
    thickness  = BOX_THICK if track.is_confirmed else 1
    x1, y1, x2, y2 = track.bbox

    # Red outer ring for high-risk tracks
    if risk_score >= 60:
        cv2.rectangle(frame, (x1-2, y1-2), (x2+2, y2+2), (0, 0, 255), 2)

    cv2.rectangle(frame, (x1, y1), (x2, y2), draw_color, thickness)

    # Short compact label — class | ID | confidence | state
    spd = getattr(track, "_pixel_speed", 0.0)
    zone_tag = f"|Z:{track.current_zone[-3:]}" if track.current_zone else ""
    risk_tag = f"|R:{risk_score}" if risk_score >= 20 else ""
    label = (
        f"{track.class_name[:4].upper()} "
        f"#{track.track_id} "
        f"{track.confidence:.0%} "
        f"{track.movement_state.value[:4]}"
        f"{zone_tag}{risk_tag}"
    )

    (lw, lh), base = cv2.getTextSize(label, FONT, 0.42, 1)
    ly = max(y1, lh + 6)
    cv2.rectangle(frame, (x1, ly-lh-4), (x1+lw+4, ly+base-2), draw_color, -1)
    cv2.putText(frame, label, (x1+2, ly-3), FONT, 0.42, (0, 0, 0), 1)

    # Trajectory trail (max 20 points)
    traj = list(track.trajectory)[-20:]
    if len(traj) > 1:
        for i in range(1, len(traj)):
            alpha = i / len(traj)
            tc    = tuple(int(c * alpha) for c in draw_color)
            cv2.line(frame, tuple(traj[i-1]), tuple(traj[i]), tc, 1)

    cv2.circle(frame, tuple(track.center), 3, draw_color, -1)


def draw_hud(frame, fps, frame_num, camera_id, tracks, paused, conf, is_night, event_log, risk_engine, show_risk=True):
    h, w   = frame.shape[:2]
    counts = {"person": 0, "vehicle": 0, "animal": 0}
    for t in tracks:
        if t.is_confirmed and t.category in counts:
            counts[t.category] += 1

    # Semi-transparent top bar
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 80), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    ts    = datetime.now().strftime("%H:%M:%S")
    dot   = "PAUSED" if paused else "LIVE"
    night = "  NIGHT" if is_night else ""
    color_dot = (0, 80, 255) if paused else (0, 220, 100)

    cv2.putText(frame, f"BORDER AI  [{dot}]{night}  {ts}", (8, 18), FONT, 0.55, (0, 200, 255), 1)
    cv2.putText(frame, f"Cam:{camera_id}  FPS:{fps:4.1f}  Frame:{frame_num:05d}  Conf:{conf:.2f}", (8, 38), FONT, 0.42, (200, 200, 200), 1)
    cv2.putText(frame, f"P:{counts['person']}  V:{counts['vehicle']}  A:{counts['animal']}", (8, 58), FONT, 0.48, (100, 255, 100), 1)

    # Top threats (only if score > 0)
    if show_risk and risk_engine:
        threats = [t for t in risk_engine.get_top_threats(camera_id, n=3) if t['risk_score'] >= 20]
        if threats:
            ts_str = "  ".join(f"T{t['track_id']}={t['risk_score']}★" for t in threats)
            cv2.putText(frame, f"Threats: {ts_str}", (8, 72), FONT, 0.38, (0, 80, 255), 1)

    # Controls hint (bottom-right, compact)
    hint = "Q=Quit S=Snap P=Pause N=Night +/-=Conf"
    (hw, _), _ = cv2.getTextSize(hint, FONT, 0.36, 1)
    cv2.rectangle(frame, (w-hw-10, h-20), (w, h), (0, 0, 0), -1)
    cv2.putText(frame, hint, (w-hw-4, h-6), FONT, 0.36, (120, 120, 120), 1)

    # Recent events (bottom-left, last 4 only)
    if event_log:
        log_y = h - 26
        for txt, sev in reversed(event_log[-4:]):
            color = SEV_COLOR.get(sev, (180, 180, 180))
            cv2.putText(frame, txt, (8, log_y), FONT, 0.36, color, 1)
            log_y -= 16
            if log_y < 90:
                break


# ─────────────────────────────────────────────────────────────
#  Main loop
# ─────────────────────────────────────────────────────────────

def process_video(source, camera_id: str, config: dict, loop_file=True, output_dir="data/output"):
    from src.video.video_source import VideoSource

    perf_cfg     = config.get("performance", {})
    show_display  = perf_cfg.get("show_display", True)
    skip_frames   = max(1, perf_cfg.get("process_every_n_frames", 1))
    display_width = perf_cfg.get("display_width", 1280)
    write_jsonl   = config.get("output", {}).get("write_jsonl", True)
    print_console = config.get("output", {}).get("print_to_console", True)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    det_file   = Path(output_dir) / "detections.jsonl"
    track_file = Path(output_dir) / "tracks.jsonl"

    # ── Load all modules ─────────────────────────────────────────────
    logger.info("Loading all AI modules...")

    detector         = Detector(config.get("model", {}))
    if not detector.load():
        logger.error("Model failed to load — cannot start.")
        return

    tracker          = Tracker(config.get("tracking", {}))
    movement_ana     = MovementAnalyzer(config.get("movement", {}))
    move_events      = MovementEventDetector(config)
    zone_manager     = ZoneManager(config)
    n_zones          = zone_manager.load_zones("config/zones.yaml")
    loitering_det    = LoiteringDetector(config, zone_manager)
    night_det        = NightDetector(config)
    group_det        = GroupMovementDetector(config)
    unusual_det      = UnusualMovementDetector(config)
    line_crossing    = LineCrossingDetector(config)
    n_lines          = line_crossing.load_lines("config/cameras.yaml")
    face_det         = FaceDetector(config)
    anpr             = ANPRModule(config)
    weapon_det       = WeaponDetector(config)
    risk_engine      = RiskEngine(config)
    health_monitor   = CameraHealthMonitor(config)
    evidence_mgr     = EvidenceManager(config)
    json_writer      = JSONWriter(output_dir)

    logger.info(
        f"All modules ready | "
        f"Zones:{n_zones} | Lines:{n_lines} | "
        f"Face:{face_det.enabled} | ANPR:{anpr.enabled} | "
        f"Weapon:{weapon_det.enabled} | "
        f"Night:{night_det.enabled} | Risk:{risk_engine.enabled}"
    )

    # ── Open video ───────────────────────────────────────────────────
    video = VideoSource(source, camera_id=camera_id)
    if not video.open():
        logger.error(f"Cannot open source: {source}")
        return

    logger.info("=" * 62)
    logger.info("  BORDER AI ENGINE v3.0 — FULLY OPERATIONAL")
    logger.info("  Press Q in the display window to quit.")
    logger.info("=" * 62)

    # ── State ────────────────────────────────────────────────────────
    fps = 0.0; fps_count = 0; fps_timer = now_ts()
    frame_num     = 0
    paused        = False
    show_faces    = True
    night_override = None
    conf          = config.get("model", {}).get("confidence_threshold", 0.45)
    event_log     = []
    snapshot_cnt  = 0
    track_risks   = {}   # track_id → risk_score

    snap_dir = Path("data/evidence") / camera_id / date_folder_name()
    snap_dir.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            if paused:
                key = cv2.waitKey(50) & 0xFF
                if key in (ord('q'), 27): break
                elif key == ord('p'):     paused = False
                continue

            ok, frame = video.read()

            # ── Camera health ─────────────────────────────────────────
            health_events = health_monitor.update(camera_id, frame if ok else None, ok)
            for he in health_events:
                json_writer.write_event(he)
                event_log.append((f"[{he.severity.value}] {he.event_type.value}", he.severity.value))

            if not ok:
                if video.is_file and loop_file:
                    video.rewind(); continue
                logger.info("Video ended.")
                break

            frame_num += 1
            if frame_num % skip_frames != 0:
                continue

            # ── Night mode ────────────────────────────────────────────
            is_night = night_override if night_override is not None else night_det.is_night_time(frame)

            # ── DETECTION ─────────────────────────────────────────────
            detections = detector.detect(frame, frame_number=frame_num, camera_id=camera_id)

            # ── TRACKING ──────────────────────────────────────────────
            tracks = tracker.update(detections, camera_id=camera_id)

            # ── MOVEMENT ──────────────────────────────────────────────
            for t in tracks:
                movement_ana.analyze(t)

            # ── EVENT PIPELINE ────────────────────────────────────────
            all_events = []

            all_events.extend(move_events.update(tracks, camera_id, frame_num))
            all_events.extend(zone_manager.update(tracks, camera_id, frame_num))
            all_events.extend(loitering_det.update(tracks, camera_id, frame_num))
            all_events.extend(night_det.update(tracks, camera_id, frame_num, is_night))
            all_events.extend(line_crossing.update(tracks, camera_id, frame_num))
            all_events.extend(group_det.update(tracks, camera_id, frame_num))
            all_events.extend(unusual_det.update(tracks, camera_id, frame_num))

            # Face detection
            face_dets, face_evts = face_det.detect(frame, tracks, camera_id, frame_num)
            all_events.extend(face_evts)

            # ANPR (vehicle tracks only)
            vehicle_tracks = [t for t in tracks if t.category == "vehicle" and t.is_confirmed]
            if anpr.enabled and vehicle_tracks:
                _, anpr_evts = anpr.process(frame, vehicle_tracks, camera_id, frame_num)
                all_events.extend(anpr_evts)

            # Weapon detection
            person_tracks = [t for t in tracks if t.category == "person"]
            if weapon_det.enabled:
                _, wpn_evts = weapon_det.detect(frame, person_tracks, camera_id, frame_num)
                all_events.extend(wpn_evts)

            # ── RISK ENGINE ───────────────────────────────────────────
            risk_engine.ingest_events(all_events)
            track_risks = {}
            for t in tracks:
                if t.is_confirmed:
                    score, _ = risk_engine.evaluate(t.track_id, camera_id, is_night)
                    track_risks[t.track_id] = score

            # ── PROCESS EVENTS ────────────────────────────────────────
            for evt in all_events:
                sev = evt.severity.value if evt.severity else "INFO"
                msg = f"  [{sev:8s}] {evt.event_type.value} | Trk:{evt.track_id}"
                logger.info(msg)
                event_log.append((f"[{sev}] {evt.event_type.value}", sev))
                if len(event_log) > 25:
                    event_log.pop(0)

                if write_jsonl:
                    json_writer.write_event(evt)

                ev_path = evidence_mgr.capture(frame, evt)
                if ev_path:
                    evt.evidence_image = ev_path

            # ── WRITE DETECTIONS / TRACKS ─────────────────────────────
            if write_jsonl:
                if detections:
                    with open(det_file, "a", encoding="utf-8") as f:
                        for d in detections:
                            rec = d.to_dict(); rec["timestamp"] = now_iso()
                            f.write(json.dumps(rec) + "\n")
                for t in tracker.get_confirmed_tracks():
                    with open(track_file, "a", encoding="utf-8") as f:
                        td = t.to_dict()
                        td.update({
                            "movement_state": t.movement_state.value,
                            "direction":      t.direction.value,
                            "pixel_speed":    round(getattr(t, "_pixel_speed", 0.0), 2),
                            "current_zone":   t.current_zone,
                            "risk_score":     track_risks.get(t.track_id, 0),
                        })
                        f.write(json.dumps(td) + "\n")

            # ── FPS ───────────────────────────────────────────────────
            fps_count += 1
            elapsed = now_ts() - fps_timer
            if elapsed >= 1.0:
                fps = fps_count / elapsed; fps_count = 0; fps_timer = now_ts()

            # ── CONSOLE LOG ───────────────────────────────────────────
            if print_console:
                for t in tracks:
                    if t.is_confirmed:
                        spd = getattr(t, "_pixel_speed", 0.0)
                        logger.info(
                            f"  [{t.category.upper():7s}] {t.class_name:12s} "
                            f"| ID:{t.track_id:3d} "
                            f"| {t.movement_state.value:12s} "
                            f"| {t.direction.value:12s} "
                            f"| {spd:.1f}px/f "
                            f"| Zone:{str(t.current_zone or 'none'):10s} "
                            f"| Risk:{track_risks.get(t.track_id, 0):3d} "
                            f"| {t.time_in_scene_str}"
                        )

            # ── DISPLAY ───────────────────────────────────────────────
            if show_display:
                df = frame.copy()
                h0, w0 = frame.shape[:2]
                if w0 > display_width:
                    sc = display_width / w0
                    df = cv2.resize(df, (int(w0*sc), int(h0*sc)))
                else:
                    sc = 1.0

                if is_night:
                    nl = df.copy()
                    cv2.rectangle(nl, (0,0), (df.shape[1], df.shape[0]), (50, 0, 0), -1)
                    cv2.addWeighted(nl, 0.15, df, 0.85, 0, df)

                zone_manager.draw_zones(df, scale=sc)
                line_crossing.draw_lines(df, scale=sc)

                for t in tracks:
                    draw_track(df, t, risk_score=track_risks.get(t.track_id, 0))

                if show_faces:
                    face_det.draw_faces(df, face_dets)

                draw_hud(df, fps, frame_num, camera_id, tracks,
                         paused, conf, is_night, event_log, risk_engine)

                cv2.imshow(f"Border AI v3 — {camera_id}", df)

            # ── KEYS ──────────────────────────────────────────────────
            key = cv2.waitKey(1) & 0xFF
            if   key in (ord('q'), 27):   break
            elif key == ord('s'):
                snapshot_cnt += 1
                sp = snap_dir / f"snap_{snapshot_cnt:04d}.jpg"
                cv2.imwrite(str(sp), frame)
                logger.info(f"Snapshot: {sp}")
            elif key == ord('p'):   paused = True
            elif key == ord('f'):   show_faces = not show_faces
            elif key == ord('n'):
                night_override = {None: True, True: False, False: None}[night_override]
                logger.info(f"Night mode: {night_override if night_override is not None else 'AUTO'}")
            elif key in (ord('+'), ord('=')):
                conf = min(0.95, conf+0.05); detector.confidence = conf
                logger.info(f"Conf → {conf:.2f}")
            elif key == ord('-'):
                conf = max(0.05, conf-0.05); detector.confidence = conf
                logger.info(f"Conf → {conf:.2f}")

    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    finally:
        video.release()
        cv2.destroyAllWindows()
        d = detector.get_stats(); t = tracker.get_stats(); j = json_writer.get_stats()
        logger.info("=" * 62)
        logger.info("  SESSION COMPLETE")
        logger.info(f"  Frames      : {d['frames_processed']}")
        logger.info(f"  Detections  : {d['total_detections']}")
        logger.info(f"  Tracks      : {t['total_tracks_created']}")
        logger.info(f"  Events      : {j['events_written']}")
        logger.info(f"  Evidence    : {evidence_mgr.saved_count} images")
        logger.info(f"  Avg FPS     : {fps:.1f}")
        logger.info(f"  Output      : {output_dir}/")
        if snapshot_cnt:
            logger.info(f"  Snapshots   : {snapshot_cnt}")
        logger.info("=" * 62)


# ─────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Border AI Analytics Engine v3.0")
    p.add_argument("--source",     type=str,   default=None)
    p.add_argument("--camera",     type=str,   default=None)
    p.add_argument("--config",     type=str,   default="config/config.yaml")
    p.add_argument("--confidence", type=float, default=None)
    p.add_argument("--no-display", action="store_true")
    p.add_argument("--loop",       action="store_true", default=True)
    return p.parse_args()


def main():
    args   = parse_args()
    config = load_config(args.config)
    log_cfg = config.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_to_file=log_cfg.get("log_to_file", True),
        log_file=log_cfg.get("log_file", "data/output/engine.log"),
    )
    logger.info("=" * 62)
    logger.info("  Border AI Analytics Engine  v3.0.0 — COMPLETE")
    logger.info("=" * 62)

    if args.confidence:
        config.setdefault("model", {})["confidence_threshold"] = args.confidence
    if args.no_display:
        config.setdefault("performance", {})["show_display"] = False

    source = camera_id = None
    if args.source:
        source    = 0 if args.source.lower() == "webcam" else args.source
        camera_id = "webcam_001" if args.source.lower() == "webcam" else "camera_001"
    elif args.camera:
        cams    = load_cameras("config/cameras.yaml")
        cam_cfg = next((c for c in cams if c["id"] == args.camera), None)
        if not cam_cfg: logger.error(f"Camera '{args.camera}' not found"); sys.exit(1)
        source, camera_id = cam_cfg["source"], cam_cfg["id"]
    else:
        cams    = load_cameras("config/cameras.yaml")
        enabled = [c for c in cams if c.get("enabled", True)]
        if not enabled: logger.error("No enabled cameras. Use --source webcam"); sys.exit(1)
        source, camera_id = enabled[0]["source"], enabled[0]["id"]

    logger.info(f"Source  : {source}")
    logger.info(f"Camera  : {camera_id}")

    process_video(
        source=source, camera_id=camera_id, config=config,
        loop_file=args.loop,
        output_dir=config.get("output", {}).get("base_dir", "data/output"),
    )


if __name__ == "__main__":
    main()
