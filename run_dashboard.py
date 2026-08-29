"""
run_dashboard.py
================
Single entry point. Starts FastAPI + AI pipeline.
Usage:
    python run_dashboard.py
    python run_dashboard.py --port 8000
    python run_dashboard.py --camera 0
    python run_dashboard.py --video path/to/video.mp4
"""

import argparse
import sys
import uvicorn
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="AI Border Surveillance Dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--camera", default=None, help="Camera index (e.g. 0) or RTSP URL")
    parser.add_argument("--video",  default=None, help="Path to video file")
    parser.add_argument("--auto-start", action="store_true", help="Auto-start webcam immediately on launch")
    parser.add_argument("--reload", action="store_true", help="Dev mode auto-reload")
    args = parser.parse_args()

    # Validate paths
    if args.video and not Path(args.video).exists():
        print(f"[ERROR] Video file not found: {args.video}")
        sys.exit(1)

    print("=" * 60)
    print("  AI BORDER SURVEILLANCE COMMAND CENTER")
    print("  Powered by YOLOv8 + FastAPI + React")
    print("=" * 60)
    print(f"  Dashboard URL: http://localhost:{args.port}")
    print(f"  API docs:      http://localhost:{args.port}/docs")
    print("  Status:        Standby (Webcam starts on UI button click)")
    print("=" * 60)

    # Optional auto-start only if --auto-start is explicitly passed
    source = None
    if args.auto_start:
        if args.camera is not None:
            source = int(args.camera) if str(args.camera).isdigit() else args.camera
        elif args.video:
            source = args.video
        else:
            source = 0

    if source is not None:
        import threading, time, requests
        def auto_start():
            for _ in range(8):
                time.sleep(1.5)
                try:
                    r = requests.post(
                        f"http://localhost:{args.port}/api/start-camera",
                        data={"source": str(source), "camera_id": "camera_001"},
                        timeout=5,
                    )
                    if r.status_code == 200:
                        print(f"[Auto-start] Pipeline started with source: {source}")
                        break
                except Exception:
                    pass
        threading.Thread(target=auto_start, daemon=True).start()

    uvicorn.run(
        "api.server:app",
        host=args.host,
        port=args.port,
        reload=getattr(args, "reload", False),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
