"""
quick_test.py — Quick YOLO Detection Test
==========================================
PURPOSE:
    Run this AFTER installation is complete.
    This script tests if YOLO is working correctly by:
    1. Loading the YOLOv8 nano model (auto-downloads if not present)
    2. Running detection on your webcam OR a video file
    3. Drawing boxes around detected people and vehicles
    4. Showing FPS and confidence scores live on screen

HOW TO RUN (after activating venv):

    # Test with your WEBCAM (press Q to quit):
    python quick_test.py --source webcam

    # Test with a VIDEO FILE:
    python quick_test.py --source path/to/your/video.mp4

    # Test with the sample video:
    python quick_test.py --source data/test_videos/test.mp4

CONTROLS:
    Q = Quit
    S = Save a snapshot of the current frame
    P = Pause / Resume
"""

import argparse
import sys
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Quick YOLO Detection Test — Border AI Analytics"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="webcam",
        help='Video source: "webcam" or path to video file (e.g. test.mp4)',
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.45,
        help="Detection confidence threshold (0.0 to 1.0, default: 0.45)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="YOLO model file (default: yolov8n.pt — downloads automatically)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ── Step 1: Import libraries ──────────────────────────────────
    print("\n" + "=" * 60)
    print("  Border AI Analytics — Quick Detection Test")
    print("=" * 60)

    print("\n[1/4] Loading libraries...")
    try:
        import cv2
        print(f"  ✅ OpenCV {cv2.__version__}")
    except ImportError:
        print("  ❌ OpenCV not found. Run: pip install opencv-python")
        sys.exit(1)

    try:
        from ultralytics import YOLO
        import ultralytics
        print(f"  ✅ Ultralytics {ultralytics.__version__}")
    except ImportError:
        print("  ❌ Ultralytics not found. Run: pip install ultralytics")
        sys.exit(1)

    try:
        import numpy as np
        print(f"  ✅ NumPy {np.__version__}")
    except ImportError:
        print("  ❌ NumPy not found. Run: pip install numpy")
        sys.exit(1)

    # ── Step 2: Load YOLO model ───────────────────────────────────
    print(f"\n[2/4] Loading YOLO model: {args.model}")
    print("      (First run will auto-download ~6MB model — please wait)")
    try:
        model = YOLO(args.model)
        print(f"  ✅ Model loaded successfully")
    except Exception as e:
        print(f"  ❌ Failed to load model: {e}")
        sys.exit(1)

    # Classes we care about (from COCO dataset)
    # Full list: https://docs.ultralytics.com/datasets/detect/coco/
    TARGET_CLASSES = {
        0: "person",
        1: "bicycle",
        2: "car",
        3: "motorcycle",
        5: "bus",
        7: "truck",
    }

    # Colors for each class (BGR format for OpenCV)
    CLASS_COLORS = {
        0: (0, 255, 0),      # person → Green
        1: (255, 165, 0),    # bicycle → Orange
        2: (0, 0, 255),      # car → Red
        3: (255, 0, 255),    # motorcycle → Magenta
        5: (0, 255, 255),    # bus → Yellow
        7: (128, 0, 255),    # truck → Purple
    }

    # ── Step 3: Open video source ─────────────────────────────────
    print(f"\n[3/4] Opening video source: {args.source}")

    if args.source.lower() == "webcam":
        cap = cv2.VideoCapture(0)
        source_name = "Webcam"
    else:
        video_path = Path(args.source)
        if not video_path.exists():
            print(f"  ❌ Video file not found: {args.source}")
            print(f"     Please provide a valid path, e.g.:")
            print(f"     python quick_test.py --source data/test_videos/test.mp4")
            sys.exit(1)
        cap = cv2.VideoCapture(str(video_path))
        source_name = video_path.name

    if not cap.isOpened():
        print(f"  ❌ Could not open video source: {args.source}")
        if args.source.lower() == "webcam":
            print("     Make sure your webcam is connected and not used by another app.")
        sys.exit(1)

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_source = cap.get(cv2.CAP_PROP_FPS) or 30
    print(f"  ✅ Opened: {source_name} ({width}x{height} @ {fps_source:.0f}fps)")

    # ── Step 4: Run detection loop ────────────────────────────────
    print(f"\n[4/4] Starting detection...")
    print(f"      Confidence threshold: {args.confidence}")
    print(f"      Detecting: {', '.join(TARGET_CLASSES.values())}")
    print()
    print("  Controls: Q = Quit | S = Save snapshot | P = Pause")
    print("=" * 60 + "\n")

    frame_count = 0
    fps_display = 0.0
    fps_timer = time.time()
    paused = False
    snapshot_count = 0

    # Create output dir for snapshots
    snapshot_dir = Path("data/output/snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                # Video ended — loop back to start
                if args.source.lower() != "webcam":
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    print("Camera disconnected.")
                    break

            frame_count += 1

            # ── Run YOLO detection ────────────────────────────────
            t_start = time.time()
            results = model(
                frame,
                conf=args.confidence,
                classes=list(TARGET_CLASSES.keys()),  # Only our target classes
                verbose=False,
            )
            inference_ms = (time.time() - t_start) * 1000

            # ── Calculate FPS ─────────────────────────────────────
            elapsed = time.time() - fps_timer
            if elapsed >= 0.5:
                fps_display = frame_count / elapsed
                frame_count = 0
                fps_timer = time.time()

            # ── Process detections ────────────────────────────────
            detection_count = 0
            annotated_frame = frame.copy()

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                for box in boxes:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    class_name = TARGET_CLASSES.get(class_id, "unknown")
                    color = CLASS_COLORS.get(class_id, (255, 255, 255))

                    # Draw bounding box
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

                    # Draw label background
                    label = f"{class_name.upper()} {confidence:.0%}"
                    (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                    cv2.rectangle(
                        annotated_frame,
                        (x1, y1 - lh - 8),
                        (x1 + lw + 4, y1),
                        color,
                        -1,  # Filled
                    )

                    # Draw label text
                    cv2.putText(
                        annotated_frame,
                        label,
                        (x1 + 2, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 0, 0),  # Black text
                        2,
                    )

                    detection_count += 1

                    # Print to console
                    print(
                        f"  DETECTED → {class_name:12s} | "
                        f"Confidence: {confidence:.0%} | "
                        f"Box: [{x1},{y1},{x2},{y2}]"
                    )

            # ── Draw HUD (Heads-Up Display) overlay ────────────────
            # Top-left info bar
            overlay = annotated_frame.copy()
            cv2.rectangle(overlay, (0, 0), (380, 90), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, annotated_frame, 0.4, 0, annotated_frame)

            cv2.putText(annotated_frame, "BORDER AI ANALYTICS",
                        (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
            cv2.putText(annotated_frame, f"FPS: {fps_display:.1f}  |  Inference: {inference_ms:.0f}ms",
                        (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            cv2.putText(annotated_frame, f"Source: {source_name}  |  Conf: {args.confidence}",
                        (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
            cv2.putText(annotated_frame, f"Detections: {detection_count}",
                        (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 255, 0) if detection_count > 0 else (100, 100, 100), 2)

            # Show window
            cv2.imshow("Border AI Analytics — Quick Test  [Q=Quit | S=Snapshot | P=Pause]",
                       annotated_frame)

        # ── Key controls ──────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:   # Q or ESC = quit
            print("\n  Exiting...")
            break
        elif key == ord('s'):               # S = save snapshot
            if not paused:
                snapshot_count += 1
                snap_path = snapshot_dir / f"snapshot_{snapshot_count:04d}.jpg"
                cv2.imwrite(str(snap_path), annotated_frame)
                print(f"\n  📸 Snapshot saved: {snap_path}")
        elif key == ord('p'):               # P = pause/resume
            paused = not paused
            print(f"\n  {'⏸  PAUSED' if paused else '▶  RESUMED'}")

    # ── Cleanup ───────────────────────────────────────────────────
    cap.release()
    cv2.destroyAllWindows()
    print("\n" + "=" * 60)
    print("  Detection test complete!")
    if snapshot_count > 0:
        print(f"  📸 {snapshot_count} snapshot(s) saved to: data/output/snapshots/")
    print("=" * 60)


if __name__ == "__main__":
    main()
