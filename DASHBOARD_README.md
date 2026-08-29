# AI Border Surveillance Command Center — Dashboard

## Overview

A professional real-time web dashboard connecting directly to the existing YOLOv8 AI pipeline.

**No fake data.** Every value comes from the actual running AI model.

## Quick Start

```bash
# 1. Install all dependencies
pip install -r requirements.txt

# 2. Build the frontend (already built — only needed after code changes)
cd frontend && npm install && npm run build && cd ..

# 3. Run the dashboard
python run_dashboard.py

# 4. Open your browser
http://localhost:8000
```

## Run Options

```bash
# Dashboard only (no auto-start camera)
python run_dashboard.py

# Dashboard + auto-start webcam
python run_dashboard.py --camera 0

# Dashboard + auto-process a video file
python run_dashboard.py --video data/test_videos/test.mp4

# Custom port
python run_dashboard.py --port 9000
```

## Dashboard Features

| Feature | Data Source | Status |
|---------|-------------|--------|
| People count | Tracker confirmed tracks (category=person) | ✅ Live |
| Vehicle count | Tracker confirmed tracks (category=vehicle) | ✅ Live |
| Animal count | Tracker confirmed tracks (category=animal) | ✅ Live |
| Tracked objects | Active confirmed tracks | ✅ Live |
| Detection table | DetectionResult per frame | ✅ Live |
| Track IDs | IoU tracker (auto-increment) | ✅ Live |
| Confidence scores | YOLO output | ✅ Live |
| Bounding boxes | YOLO output | ✅ Live |
| Movement state | MovementAnalyzer per track | ✅ Live |
| Direction | MovementAnalyzer per track | ✅ Live |
| Zone | ZoneManager (config/zones.yaml) | ✅ Live |
| Events | Zone/behavior/health events | ✅ Live |
| Risk score | RiskEngine 0-100 decaying | ✅ Live |
| FPS | Measured in pipeline loop | ✅ Live |
| Camera status | CameraHealthMonitor | ✅ Live |
| Model name | config.yaml → model.path | ✅ Live |
| Night mode | NightDetector | ✅ Live |
| Face detections | OpenCV Haar cascade | ✅ Live (no recognition) |
| ANPR | easyocr | ⚠️ Disabled (enabled: false in config) |
| Weapon detection | Specialized model | ⚠️ Disabled (enabled: false in config) |
| Annotated video | OpenCV draw on real frames | ✅ Live MJPEG stream |

## Architecture

```
Webcam / Video / Image
         ↓
  api/pipeline_runner.py
  (wraps existing AI modules)
         ↓
  YOLO → Tracker → ZoneManager → RiskEngine
         ↓
  PipelineState (thread-safe shared state)
         ↓
  api/server.py (FastAPI)
         ↓
  /ws WebSocket → every 150ms
  /api/stream → MJPEG annotated frames
         ↓
  frontend/dist → React dashboard
         ↓
  Browser at http://localhost:8000
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | System/model/camera status |
| GET | `/api/config` | Model config from config.yaml |
| GET | `/api/cameras` | Camera list from cameras.yaml |
| GET | `/api/events` | Recent event log |
| GET | `/api/zones` | Zone config from zones.yaml |
| GET | `/api/stream` | MJPEG annotated live stream |
| POST | `/api/start-camera` | Start pipeline (source, camera_id) |
| POST | `/api/stop-camera` | Stop pipeline |
| POST | `/api/detect/image` | Upload image → YOLO → annotated result |
| POST | `/api/detect/video/start` | Upload video → start processing |
| WS | `/ws` | Real-time AI state (150ms updates) |

## WebSocket Message Format

```json
{
  "timestamp": "2026-08-30T14:32:18",
  "camera_id": "camera_001",
  "fps": 24.1,
  "model": "yolov8n.pt",
  "processing": true,
  "camera_status": "online",
  "is_night": false,
  "risk_score": 45,
  "risk_level": "MEDIUM",
  "counts": { "person": 2, "vehicle": 1, "animal": 0, "total": 3, "tracked": 3 },
  "detections": [
    {
      "track_id": 1, "class_name": "person", "category": "person",
      "confidence": 0.94, "bbox": [100, 120, 200, 350],
      "movement_state": "NORMAL", "direction": "RIGHT",
      "is_confirmed": true, "current_zone": null,
      "risk_score": 45, "time_in_scene": 12.3
    }
  ],
  "events": [...],
  "module_status": { "anpr": false, "weapon": false, "face": true, "zones": 2 }
}
```

## Project Structure (after dashboard)

```
SIH-main/
├── api/
│   ├── __init__.py
│   ├── pipeline_runner.py   ← Background AI thread
│   └── server.py            ← FastAPI + WebSocket
├── frontend/
│   ├── src/
│   │   ├── App.tsx          ← Full dashboard
│   │   ├── useWebSocket.ts  ← WS hook
│   │   ├── api.ts           ← REST client
│   │   └── types.ts         ← TypeScript types
│   └── dist/                ← Built output (served by FastAPI)
├── src/                     ← ORIGINAL AI modules (unchanged)
├── config/
├── run_dashboard.py         ← Single entry point
└── requirements.txt         ← Updated with FastAPI etc.
```

## Enabling Disabled Modules

### ANPR
```bash
pip install easyocr
# Then in config/config.yaml:
# anpr:
#   enabled: true
```

### Weapon Detection
```
# Train or obtain a specialized weapon detection model
# Place at: models/weapon/weapon_detector.pt
# Then in config/config.yaml:
# weapon_detection:
#   enabled: true
#   model_path: "models/weapon/weapon_detector.pt"
```
