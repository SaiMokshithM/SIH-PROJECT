"""
training/extract_frames.py
===========================
PURPOSE:
    Extract frames from CCTV video files for dataset creation.

    Features:
    - Extracts every Nth frame (configurable)
    - Removes near-duplicate frames (blur detection)
    - Saves to organized directory structure
    - Generates frame manifest CSV

HOW TO USE:
    python training/extract_frames.py \
        --input data/input/cctv_recording.mp4 \
        --output training/datasets/raw_frames \
        --every 5 \
        --deduplicate

AFTER THIS:
    Annotate extracted frames using:
    - Roboflow (https://roboflow.com) — recommended, has YOLO export
    - LabelImg (pip install labelImg)
    - CVAT (https://cvat.ai)

    Then run: python training/prepare_dataset.py
"""

import argparse
import cv2
import csv
import hashlib
import numpy as np
from pathlib import Path


def is_blurry(frame: np.ndarray, threshold: float = 100.0) -> bool:
    """Check if frame is too blurry to be useful for training."""
    gray      = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()
    return laplacian < threshold


def frame_hash(frame: np.ndarray) -> str:
    """Generate a hash for duplicate detection."""
    small = cv2.resize(frame, (32, 32))
    return hashlib.md5(small.tobytes()).hexdigest()


def extract_frames(
    input_path: str,
    output_dir: str,
    every_n: int = 5,
    deduplicate: bool = True,
    skip_blurry: bool = True,
    blur_threshold: float = 80.0,
    max_frames: int = 0,
) -> int:
    """
    Extract frames from video.

    Args:
        input_path:     Path to video file
        output_dir:     Directory to save frames
        every_n:        Extract every Nth frame
        deduplicate:    Skip near-duplicate frames
        skip_blurry:    Skip blurry/dark frames
        blur_threshold: Laplacian variance threshold
        max_frames:     Maximum frames to extract (0 = unlimited)

    Returns:
        Number of frames extracted
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"ERROR: Video not found: {input_path}")
        return 0

    cap         = cv2.VideoCapture(str(input_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps          = cap.get(cv2.CAP_PROP_FPS)

    print(f"Video: {input_path.name}")
    print(f"Total frames: {total_frames} | FPS: {fps:.1f}")
    print(f"Extracting every {every_n} frames...")

    saved_hashes = set()
    frame_count  = 0
    saved_count  = 0
    manifest     = []

    stem = input_path.stem

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_count += 1
            if frame_count % every_n != 0:
                continue

            # Skip blurry
            if skip_blurry and is_blurry(frame, blur_threshold):
                continue

            # Deduplicate
            if deduplicate:
                h = frame_hash(frame)
                if h in saved_hashes:
                    continue
                saved_hashes.add(h)

            # Save
            filename = f"{stem}_frame_{frame_count:07d}.jpg"
            save_path = output_dir / filename
            cv2.imwrite(str(save_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            saved_count += 1
            manifest.append({
                "filename":     filename,
                "source":       input_path.name,
                "frame_number": frame_count,
                "timestamp_s":  round(frame_count / max(fps, 1), 2),
            })

            if saved_count % 100 == 0:
                print(f"  Saved {saved_count} frames...")

            if max_frames and saved_count >= max_frames:
                print(f"  Reached max_frames limit ({max_frames})")
                break

    finally:
        cap.release()

    # Save manifest
    manifest_path = output_dir / "manifest.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "source", "frame_number", "timestamp_s"])
        writer.writeheader()
        writer.writerows(manifest)

    print(f"\nExtracted {saved_count} frames → {output_dir}")
    print(f"Manifest: {manifest_path}")
    return saved_count


def parse_args():
    parser = argparse.ArgumentParser(description="Extract frames from CCTV video for training")
    parser.add_argument("--input",     required=True, help="Input video file path")
    parser.add_argument("--output",    required=True, help="Output directory for frames")
    parser.add_argument("--every",     type=int, default=5, help="Extract every Nth frame (default: 5)")
    parser.add_argument("--max",       type=int, default=0, help="Max frames to extract (0=unlimited)")
    parser.add_argument("--no-dedup",  action="store_true", help="Disable duplicate removal")
    parser.add_argument("--no-blur",   action="store_true", help="Disable blur filtering")
    parser.add_argument("--blur-threshold", type=float, default=80.0)
    return parser.parse_args()


def main():
    args = parse_args()
    count = extract_frames(
        input_path=args.input,
        output_dir=args.output,
        every_n=args.every,
        deduplicate=not args.no_dedup,
        skip_blurry=not args.no_blur,
        blur_threshold=args.blur_threshold,
        max_frames=args.max,
    )
    print(f"Done. {count} frames extracted.")


if __name__ == "__main__":
    main()
