# models/README.md
# AI Model Weights — Download Instructions

## Why This Folder Exists

YOLO model weight files (.pt) are large binary files (6–200 MB).
They are NOT stored in Git. You must download them separately.

## Automatic Download (Easiest)

When you run the system for the first time, the model downloads automatically:

```powershell
# Just run the system — it downloads yolov8n.pt if not present
python src/main.py --source data/test_videos/test.mp4
```

## Manual Download

If automatic download fails (e.g., no internet on the target machine):

1. Visit: https://github.com/ultralytics/assets/releases
2. Download the model you need (see table below)
3. Place the .pt file in this folder (models/)
4. Update config/config.yaml:
   ```yaml
   model:
     path: "models/yolov8n.pt"
   ```

## Model Comparison

| File | Size | CPU Speed | GPU Speed | Use Case |
|------|------|-----------|-----------|----------|
| yolov8n.pt | 6 MB | ~15 FPS | ~200 FPS | Development / low-power laptop |
| yolov8s.pt | 22 MB | ~8 FPS | ~120 FPS | Better accuracy, still fast |
| yolov8m.pt | 52 MB | ~3 FPS | ~80 FPS | High accuracy, needs GPU |
| yolov8l.pt | 87 MB | ~1 FPS | ~50 FPS | Best COCO accuracy |

**Recommendation for academic demo: yolov8n.pt** (default)

## Custom Trained Model

After Phase 35 (custom training), place your custom model here:
- models/border_custom_v1.pt

Then update config.yaml to point to it.

## What These Models Detect (COCO Classes)

The pretrained models detect 80 object categories.
We filter to only use these for our system:
- person (class 0)
- bicycle (class 1)
- car (class 2)
- motorcycle (class 3)
- bus (class 5)
- truck (class 7)

All other classes are ignored by our configuration.
