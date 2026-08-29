---
title: Border Surveillance Command Center
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
license: mit
---

# AI-Based Intelligent Video Analytics Platform
## For Border Surveillance Using Existing CCTV Infrastructure

> **Academic Project** | Python + YOLO + OpenCV | Windows 11

---

## 🎯 Project Objective

Build an AI-powered CCTV video analytics engine that can:
- Detect people and vehicles in real-time
- Track objects with consistent IDs across frames
- Monitor configurable virtual zones and boundaries
- Generate structured security events (not automated actions)
- Support human operators in reviewing CCTV footage

**All final decisions remain with authorized human operators.**

---

## 🏗️ Architecture

```
CCTV / Video File
      ↓
Video Input Module          ← reads frames from file or RTSP
      ↓
Frame Processor             ← resizes, normalizes frames
      ↓
YOLO Object Detector        ← detects people/vehicles
      ↓
Object Tracker              ← assigns consistent IDs
      ↓
Movement Analyzer           ← direction, speed, patterns
      ↓
Zone / Line Engine          ← polygon zones, virtual lines
      ↓
Behavior Engine             ← loitering, intrusion, crowd
      ↓
Severity / Risk Engine      ← INFO / LOW / MEDIUM / HIGH / CRITICAL
      ↓
Evidence Manager ←→ Event Manager
      ↓
JSON Output → Future Spring Boot API → Security Dashboard
```

---

## ✨ Features

| Feature | Status |
|---|---|
| Person Detection | ✅ Phase 5 |
| Vehicle Detection | ✅ Phase 5 |
| Object Tracking | ✅ Phase 7 |
| Movement Analysis | ✅ Phase 8 |
| Polygon Zone Monitoring | ✅ Phase 9 |
| Restricted Zone Intrusion | ✅ Phase 10 |
| Virtual Line Crossing | ✅ Phase 11 |
| Loitering Detection | ✅ Phase 12 |
| Crowd / Density Detection | ✅ Phase 13 |
| Abandoned Object Framework | ✅ Phase 14 |
| Event Engine + Deduplication | ✅ Phase 15 |
| Severity & Risk Score | ✅ Phase 16 |
| Evidence Snapshots | ✅ Phase 17 |
| JSON / JSONL Output | ✅ Phase 18 |
| Camera Health Monitoring | ✅ Phase 19 |
| RTSP Stream Support | ✅ Phase 20 |
| Unit Tests | ✅ Phase 21 |
| API-Ready Output | ✅ Phase 23 |

---

## 📋 Requirements

- Windows 10/11
- Python 3.10 or 3.11 (recommended)
- 8 GB RAM minimum
- NVIDIA GPU (optional — CPU works but slower)
- No internet required after initial model download

---

## 🚀 Installation

### Step 1 — Create virtual environment
```powershell
cd border_ai_analytics
python -m venv venv
.\venv\Scripts\activate
```

### Step 2 — Install dependencies
```powershell
pip install -r requirements.txt
```

### Step 3 — Verify installation
```powershell
python phase1_verify.py
```

---

## 🤖 Model Setup

The YOLOv8 nano model (`yolov8n.pt`) is downloaded automatically on first run.

| Model | Size | Speed (CPU) | Accuracy |
|---|---|---|---|
| yolov8n.pt | 6 MB | ~15 FPS | Good |
| yolov8s.pt | 22 MB | ~8 FPS | Better |
| yolov8m.pt | 52 MB | ~3 FPS | Best |

For development, use `yolov8n.pt` (configured by default).

---

## 🎬 Running the System

```powershell
# Demo mode with a video file
python src/main.py --source data/test_videos/test.mp4

# With a specific camera configuration
python src/main.py --camera camera_001

# With custom config file
python src/main.py --config config/config.yaml
```

---

## ⚙️ Configuration

All settings are in `config/`:
- `config.yaml` — model, tracking, events, performance
- `cameras.yaml` — camera sources and RTSP URLs
- `zones.yaml` — polygon zones and virtual line coordinates

**Never hard-code settings in Python files.**

---

## 📁 Output

```
data/
├── output/
│   ├── events.jsonl       ← one event per line (JSON)
│   ├── detections.jsonl   ← all detections
│   ├── metrics.json       ← session metrics
│   └── engine.log         ← application log
└── evidence/
    └── camera_001/
        └── 2026-08-29/
            └── evt_000001.jpg
```

---

## 📊 Event JSON Schema

```json
{
  "event_id": "evt_000001",
  "camera_id": "camera_001",
  "timestamp": "2026-08-29T18:30:25",
  "event_type": "RESTRICTED_ZONE_INTRUSION",
  "severity": "HIGH",
  "risk_score": 82,
  "track_id": 17,
  "object_type": "person",
  "confidence": 0.93,
  "zone_id": "zone_001",
  "description": "Person entered configured restricted zone",
  "evidence_image": "data/evidence/camera_001/evt_000001.jpg"
}
```

---

## ⚠️ Limitations

1. **No geographic coordinates** — pixel positions only, not real-world GPS
2. **Pixel speed ≠ real speed** — reported as `estimated_pixel_speed`
3. **Low-light** reduces accuracy
4. **Rain/fog** reduces detection performance
5. **Occlusion** can cause tracking ID changes
6. **False positives/negatives** can occur — human review is required
7. **No facial recognition** — the system does NOT identify people
8. **No identity inference** — objects are tracked, not identified
9. **Loitering ≠ threat** — it means "prolonged presence" only
10. **Severity = operational priority**, not threat probability

---

## 🔒 Privacy & Ethics

This system:
- ✅ Detects objects and movement patterns
- ✅ Monitors configured zones
- ✅ Alerts human operators
- ❌ Does NOT identify individuals
- ❌ Does NOT perform facial recognition
- ❌ Does NOT make autonomous security decisions
- ❌ Does NOT control physical systems

---

## 🧪 Testing

```powershell
python -m pytest tests/ -v
```

---

## 🔮 Future Integration

The JSON output is designed for Spring Boot REST API:
```
POST /api/ai/events
```

Future expansions: WebSocket live feed, Kafka streaming, MQTT.

---

## 📈 Performance Optimization

If FPS is too low:
1. Increase `process_every_n_frames` in `config.yaml`
2. Switch to smaller model (`yolov8n.pt`)
3. Reduce `display_width`
4. Use GPU if available

---

*Academic prototype — not for production deployment without proper security review.*
"# SIH" 
