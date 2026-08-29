"""
training/train_detector.py
===========================
PURPOSE:
    Train a custom YOLO model on your own annotated dataset.

    Use this for:
    1. General object detector with your specific CCTV environment
    2. Weapon detection (specialized)
    3. Vehicle sub-class detection
    4. Any custom object class

HOW TO USE:
    Step 1: Prepare your dataset
        python training/prepare_dataset.py --input data/raw --output training/datasets/my_dataset

    Step 2: Train
        python training/train_detector.py --data training/datasets/my_dataset/data.yaml --epochs 50

    Step 3: Validate
        python training/validate_model.py --model runs/detect/train/weights/best.pt --data ...

    Step 4: Test
        python training/test_model.py --model runs/detect/train/weights/best.pt --source data/test_videos/test.mp4

    Step 5: Deploy
        Copy best.pt to models/object/custom_detector.pt
        Update config.yaml: model.path: "models/object/custom_detector.pt"

REQUIREMENTS:
    pip install ultralytics
    Annotate data with Roboflow, LabelImg, or CVAT (YOLO format)

DATA SPLIT RULE:
    70% training | 20% validation | 10% testing
    Split by video sequence (not by frame) to prevent data leakage.

WEAPON TRAINING NOTE:
    Use ONLY legally obtained, authorized datasets.
    Do NOT mix weapon classes into general model.
    Train a separate weapon_detector model.
    See: training/weapon_training_guide.md
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def parse_args():
    parser = argparse.ArgumentParser(description="Train custom YOLO detector")
    parser.add_argument("--data",    required=True,  help="Path to data.yaml file")
    parser.add_argument("--model",   default="yolov8n.pt", help="Base model (yolov8n/s/m/l/x.pt)")
    parser.add_argument("--epochs",  type=int, default=50)
    parser.add_argument("--imgsz",   type=int, default=640)
    parser.add_argument("--batch",   type=int, default=16)
    parser.add_argument("--device",  default="auto")
    parser.add_argument("--project", default="runs/detect", help="Output directory")
    parser.add_argument("--name",    default="train",       help="Run name")
    parser.add_argument("--type",    default="general",
                        choices=["general", "weapon", "face", "plate"],
                        help="Type of detector being trained")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print(f"  Border AI — Custom Detector Training")
    print(f"  Type:    {args.type}")
    print(f"  Data:    {args.data}")
    print(f"  Model:   {args.model}")
    print(f"  Epochs:  {args.epochs}")
    print(f"  ImgSize: {args.imgsz}")
    print("=" * 60)

    if args.type == "weapon":
        print("\n  WEAPON TRAINING NOTICE:")
        print("  - Only use legally authorized datasets")
        print("  - This creates a SEPARATE weapon detector model")
        print("  - Output will go to: models/weapon/")
        print("  - Review all detections manually before deployment\n")

    if not Path(args.data).exists():
        print(f"ERROR: data.yaml not found at: {args.data}")
        print("  Run prepare_dataset.py first to set up your dataset.")
        sys.exit(1)

    try:
        from ultralytics import YOLO
        model = YOLO(args.model)

        device = args.device
        if device == "auto":
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"  Training on: {device}")
        print("  Starting training...\n")

        results = model.train(
            data=args.data,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=device,
            project=args.project,
            name=args.name,
            patience=15,
            save=True,
            cache=False,
            verbose=True,
        )

        best_model = Path(args.project) / args.name / "weights" / "best.pt"
        print("\n" + "=" * 60)
        print("  Training complete!")
        print(f"  Best model: {best_model}")
        print(f"  Metrics: mAP50={results.results_dict.get('metrics/mAP50(B)', 'N/A'):.4f}")

        if args.type == "weapon":
            print(f"\n  Deploy: cp {best_model} models/weapon/weapon_detector.pt")
        elif args.type == "general":
            print(f"\n  Deploy: cp {best_model} models/object/custom_detector.pt")
        print("=" * 60)

    except ImportError:
        print("ERROR: ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)
    except Exception as e:
        print(f"Training error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
