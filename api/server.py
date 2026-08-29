"""
api/server.py
=============
FastAPI server providing:
- REST endpoints: /api/config, /api/cameras, /api/status, /api/events
- POST /api/detect/image  — image upload → real YOLO inference → annotated result
- POST /api/start-camera  — start live camera/video pipeline
- POST /api/stop-camera   — stop pipeline
- GET  /api/stream        — MJPEG stream of annotated live frames
- WS   /ws                — WebSocket pushing real-time AI state every ~150ms
"""

import sys
import io
import cv2
import yaml
import asyncio
import numpy as np
from pathlib import Path
import time
from typing import Optional, Set, List
from datetime import datetime
from pydantic import BaseModel

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config_loader import load_config
from src.auth.auth_manager import AuthManager, get_current_authority, UserRole
from src.audit.audit_logger import audit_logger
from api.pipeline_runner import PipelineRunner, state

# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="AI Border Surveillance API & Authority Portal", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global pipeline runner (initialized at startup)
runner: Optional[PipelineRunner] = None
config: dict = {}
cameras_config: dict = {}
runner_start_time: float = time.time()

# Connected WebSocket clients
ws_clients: Set[WebSocket] = set()

# Models
class LoginRequest(BaseModel):
    username: Optional[str] = "commander"
    pin: Optional[str] = "9926"

class IncidentActionRequest(BaseModel):
    actor: Optional[str] = "Commander"
    notes: Optional[str] = None


# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global runner, config, cameras_config, runner_start_time
    runner_start_time = time.time()
    config = load_config("config/config.yaml")
    try:
        with open("config/cameras.yaml", "r") as f:
            cameras_config = yaml.safe_load(f)
    except Exception:
        cameras_config = {}

    print("[Server] Loading AI model...")
    runner = PipelineRunner(config)
    ok = runner.load_model()
    if not ok:
        print("[Server] WARNING: Model failed to load!")
    else:
        print(f"[Server] Model loaded: {state.model_name}")

    # Start WebSocket broadcast loop
    asyncio.create_task(ws_broadcast_loop())


@app.on_event("shutdown")
async def shutdown():
    if runner:
        runner.stop()


# ── WebSocket broadcast loop ──────────────────────────────────────────────────

async def ws_broadcast_loop():
    """Push AI state to all connected WebSocket clients every 150ms."""
    while True:
        await asyncio.sleep(0.15)
        if not ws_clients:
            continue
        try:
            msg = state.to_ws_message()
            import json
            payload = json.dumps(msg)
            dead = set()
            for ws in list(ws_clients):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.add(ws)
            ws_clients.difference_update(dead)
        except Exception as e:
            print(f"[WS Broadcast] Error: {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    print(f"[WS] Client connected. Total: {len(ws_clients)}")
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except Exception:
        pass
    finally:
        ws_clients.discard(websocket)
        print(f"[WS] Client disconnected. Total: {len(ws_clients)}")


# ── MJPEG Stream ─────────────────────────────────────────────────────────────

async def mjpeg_generator():
    """Yield annotated frames as MJPEG stream."""
    try:
        while True:
            await asyncio.sleep(0.033)  # ~30fps max
            with state.lock:
                jpeg = state.frame_jpeg
            if jpeg is None:
                # Send a black placeholder frame
                blank = np.zeros((360, 640, 3), dtype=np.uint8)
                cv2.putText(blank, "Waiting for camera...", (120, 180),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 2)
                _, buf = cv2.imencode(".jpg", blank)
                jpeg = buf.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )
    except Exception:
        return


@app.get("/api/stream")
async def video_stream():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace;boundary=frame",
    )


# ── Authentication & Security Clearance ──────────────────────────────────────

@app.post("/api/auth/login")
async def auth_login(req: LoginRequest):
    """Authenticate authority / operator using PIN or username."""
    session = AuthManager.authenticate(req.username or "commander", req.pin)
    if not session:
        raise HTTPException(401, "Invalid security clearance PIN or credentials.")
    audit_logger.log(
        action="AUTHORITY_LOGIN",
        actor=session["name"],
        role=session["role"],
        details=f"Security clearance established ({session['department']})"
    )
    return session


@app.get("/api/auth/me")
async def auth_me(authority: dict = Depends(get_current_authority)):
    """Verify active security clearance token."""
    return authority


@app.post("/api/auth/logout")
async def auth_logout(token: Optional[str] = Header(None)):
    if token:
        AuthManager.revoke_token(token)
    return {"status": "logged_out"}


# ── REST: Status & Config ─────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    with state.lock:
        return {
            "system": "online",
            "model": state.model_name,
            "camera_id": state.camera_id,
            "camera_status": state.camera_status,
            "processing": state.processing,
            "fps": round(state.fps, 1),
            "last_update": state.last_update,
            "risk_score": state.risk_score,
            "risk_level": state.risk_level,
            "is_night": state.is_night,
            "frame_number": state.frame_number,
            "module_status": {
                "anpr": state.anpr_enabled,
                "weapon": state.weapon_enabled,
                "face": state.face_enabled,
                "zones_loaded": state.zones_loaded,
            },
        }


@app.get("/api/config")
async def get_config():
    model_cfg = config.get("model", {})
    return {
        "model_path": model_cfg.get("path", "yolov8n.pt"),
        "confidence_threshold": model_cfg.get("confidence_threshold", 0.45),
        "detect_classes": model_cfg.get("detect_classes", []),
        "tracking_enabled": config.get("tracking", {}).get("enabled", True),
        "anpr_enabled": config.get("anpr", {}).get("enabled", False),
        "weapon_enabled": config.get("weapon_detection", {}).get("enabled", False),
        "face_enabled": config.get("face_detection", {}).get("enabled", True),
    }


@app.get("/api/cameras")
async def get_cameras():
    cams = cameras_config.get("cameras", [])
    result = []
    for c in cams:
        cam_id = c.get("id", "")
        with state.lock:
            is_active = (cam_id == state.camera_id and state.camera_status == "online")
        result.append({
            "id": cam_id,
            "name": c.get("name", cam_id),
            "location": c.get("location", ""),
            "enabled": c.get("enabled", False),
            "status": "online" if is_active else ("offline" if c.get("enabled") else "disabled"),
            "source": c.get("source", ""),
        })
    return result


@app.get("/api/events")
async def get_events(limit: int = 50):
    with state.lock:
        evts = state.recent_events[-limit:]
    return [
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
            "status": e.status,
            "evidence_path": e.evidence_path,
        }
        for e in evts
    ]


# ── Incident Management ───────────────────────────────────────────────────────

@app.get("/api/incidents")
async def get_incidents(
    limit: int = 100,
    severity: Optional[str] = None,
    status_filter: Optional[str] = None,
    camera_id: Optional[str] = None,
):
    """Retrieve full incident dossiers with real state, newest first."""
    with state.lock:
        evts = list(reversed(state.recent_events))

    results = []
    for e in evts:
        if severity and e.severity.upper() != severity.upper():
            continue
        if status_filter and e.status.upper() != status_filter.upper():
            continue
        if camera_id and e.camera_id != camera_id:
            continue
        results.append({
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
            "status": e.status,
            "evidence_path": e.evidence_path,
            "acknowledged_by": e.acknowledged_by,
            "acknowledged_at": e.acknowledged_at,
            "resolved_by": e.resolved_by,
            "resolved_at": e.resolved_at,
            "resolution_notes": e.resolution_notes,
            "confidence": e.confidence,
            "bbox": e.bbox,
        })
        if len(results) >= limit:
            break
    return results


@app.post("/api/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, req: Optional[IncidentActionRequest] = None):
    """Acknowledge an incident and log action to security audit."""
    actor = req.actor if req and req.actor else "Commander"
    if not runner:
        raise HTTPException(500, "Pipeline runner not initialized")
    updated = runner.update_incident(incident_id, "ACKNOWLEDGED", actor=actor)
    if not updated:
        raise HTTPException(404, f"Incident {incident_id} not found")
    return {"status": "acknowledged", "incident_id": incident_id, "by": actor}


@app.post("/api/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, req: Optional[IncidentActionRequest] = None):
    """Resolve an incident with notes and log to audit trail."""
    actor = req.actor if req and req.actor else "Commander"
    notes = req.notes if req and req.notes else "Threat verified and mitigated."
    if not runner:
        raise HTTPException(500, "Pipeline runner not initialized")
    updated = runner.update_incident(incident_id, "RESOLVED", actor=actor, notes=notes)
    if not updated:
        raise HTTPException(404, f"Incident {incident_id} not found")
    return {"status": "resolved", "incident_id": incident_id, "by": actor, "notes": notes}


# ── Authority Diagnostics & Evidence ─────────────────────────────────────────

@app.get("/api/authority/audit")
async def get_audit_logs(limit: int = 50):
    """Return chronological authority audit logs."""
    return audit_logger.get_logs(limit=limit)


@app.get("/api/authority/system-health")
async def get_system_health():
    """Return deep operational diagnostic telemetry."""
    with state.lock:
        confirmed_count = len([d for d in state.detections if d.is_confirmed])
        return {
            "system_status": "OPERATIONAL" if state.camera_status in ("online", "offline") else "DEGRADED",
            "uptime_seconds": round(time.time() - runner_start_time, 1),
            "camera_status": state.camera_status,
            "fps": round(state.fps, 1),
            "frame_number": state.frame_number,
            "active_tracks": confirmed_count,
            "session_events": state.event_count_session,
            "ws_connected_clients": len(ws_clients),
            "subsystems": {
                "yolo_detector": {"status": "ACTIVE", "model": state.model_name},
                "weapon_detector": {"status": "ACTIVE" if state.weapon_enabled else "OFFLINE"},
                "anpr_engine": {"status": "ACTIVE" if state.anpr_enabled else "OFFLINE"},
                "face_detector": {"status": "ACTIVE" if state.face_enabled else "OFFLINE"},
                "risk_engine": {"status": "ACTIVE", "score": state.risk_score, "level": state.risk_level},
                "zones_engine": {"status": "ACTIVE", "zones_loaded": state.zones_loaded},
            }
        }


@app.get("/api/evidence-list")
async def get_evidence_list(limit: int = 50):
    """Return real evidence image files captured by the system."""
    ev_dir = project_root / "data" / "evidence"
    results = []
    if ev_dir.exists():
        for p in sorted(ev_dir.glob("**/*.jpg"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            results.append({
                "filename": p.name,
                "path": f"/api/evidence/{p.relative_to(project_root).as_posix()}",
                "size_bytes": p.stat().st_size,
                "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            })
    return results


@app.get("/api/evidence/{file_path:path}")
async def get_evidence_file(file_path: str):
    """Serve real evidence images securely."""
    clean_path = Path(file_path).name
    # Search in data/evidence and data/output/faces
    candidates = list(project_root.glob(f"data/evidence/**/{clean_path}")) + \
                 list(project_root.glob(f"data/output/faces/**/{clean_path}")) + \
                 list(project_root.glob(f"data/uploads/**/{clean_path}"))
    if candidates and candidates[0].exists():
        return FileResponse(candidates[0], media_type="image/jpeg")
    raise HTTPException(404, "Evidence image not found on disk")


@app.get("/api/zones")
async def get_zones():
    try:
        zones_file = project_root / "config" / "zones.yaml"
        with open(zones_file, "r", encoding="utf-8") as f:
            zones_data = yaml.safe_load(f)
        return zones_data or {"zones": []}
    except Exception as e:
        print(f"[get_zones] Error: {e}")
        return {"zones": []}


# ── Camera Control ────────────────────────────────────────────────────────────

@app.post("/api/start-camera")
async def start_camera(source: str = Form("0"), camera_id: str = Form("camera_001")):
    if runner is None:
        raise HTTPException(500, "Pipeline not initialized")

    # Stop existing if running
    runner.stop()
    await asyncio.sleep(0.5)

    # source "0" = webcam, else treat as path/URL
    src = int(source) if source.isdigit() else source
    runner.start(src, camera_id=camera_id)
    return {"status": "started", "source": source, "camera_id": camera_id}


@app.post("/api/stop-camera")
async def stop_camera():
    if runner:
        runner.stop()
    return {"status": "stopped"}


# ── Image Detection ───────────────────────────────────────────────────────────

@app.post("/api/detect/image")
async def detect_image(file: UploadFile = File(...)):
    """Upload an image → run real YOLO → return annotated image + detections."""
    if runner is None:
        raise HTTPException(500, "Pipeline not initialized")

    allowed = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type: {suffix}")

    contents = await file.read()
    max_size = 20 * 1024 * 1024  # 20MB
    if len(contents) > max_size:
        raise HTTPException(400, "File too large (max 20MB)")

    np_arr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Cannot decode image")

    # Run actual YOLO inference
    result = runner.process_image(img, camera_id="image_upload")

    import base64
    jpeg_b64 = base64.b64encode(result["jpeg"]).decode()

    return {
        "annotated_image": f"data:image/jpeg;base64,{jpeg_b64}",
        "detections": result["detections"],
        "counts": result["counts"],
        "events": result.get("events", []),
        "model": state.model_name,
        "timestamp": datetime.now().isoformat(),
    }


# ── Video Processing ──────────────────────────────────────────────────────────

@app.post("/api/detect/video/start")
async def start_video_processing(file: UploadFile = File(...)):
    """Upload a video → process with AI → stream as MJPEG."""
    if runner is None:
        raise HTTPException(500, "Pipeline not initialized")

    allowed = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported video type: {suffix}")

    import time, re
    uploads_dir = project_root / "data" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)
    save_path = uploads_dir / f"upload_{int(time.time())}_{safe_name}"

    try:
        with open(save_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
    except Exception as e:
        raise HTTPException(500, f"Failed to save video: {str(e)}")

    runner.stop()
    await asyncio.sleep(0.3)
    runner.start(str(save_path), camera_id="video_upload")
    return {"status": "started", "filename": file.filename}


# ── Serve Frontend ────────────────────────────────────────────────────────────

frontend_dist = project_root / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        index = frontend_dist / "index.html"
        return HTMLResponse(content=index.read_text(encoding="utf-8"))

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_spa(full_path: str):
        if full_path.startswith("api") or full_path == "ws":
            raise HTTPException(404)
        index = frontend_dist / "index.html"
        return HTMLResponse(content=index.read_text(encoding="utf-8"))
