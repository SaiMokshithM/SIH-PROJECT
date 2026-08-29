"""
phase1_verify.py — Phase 1 Verification Script
===============================================
PURPOSE:
    This script checks that ALL required libraries are installed correctly
    before we write any AI code. Run this first. If it passes, Phase 1 is done.

HOW TO RUN:
    python phase1_verify.py

EXPECTED OUTPUT:
    All green checkmarks → you're ready for Phase 2.
    Any red ✗ → follow the fix instructions shown.
"""

import sys
import os

# Fix Windows terminal encoding so output displays correctly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore


def check(label: str, fn) -> bool:
    """Run a single check and print a formatted result."""
    try:
        result = fn()
        print(f"  ✅  {label}: {result}")
        return True
    except Exception as e:
        print(f"  ❌  {label}: FAILED — {e}")
        return False


def main():
    print("=" * 60)
    print("  Border AI Analytics — Phase 1 Verification")
    print("=" * 60)
    print()

    passed = 0
    total = 0

    # ── 1. Python version ────────────────────────────────────────
    print("[ Python ]")
    total += 1
    v = sys.version_info
    ok = check(
        "Python version",
        lambda: f"{v.major}.{v.minor}.{v.micro}"
    )
    if ok and v.major == 3 and v.minor >= 9:
        passed += 1
    elif ok:
        print("    ⚠️  Python 3.9+ recommended. You have an older version.")
    print()

    # ── 2. Core libraries ────────────────────────────────────────
    print("[ Core Libraries ]")

    checks = [
        ("numpy",     "import numpy as np; print(np.__version__)",     "NumPy (array math)"),
        ("cv2",       "import cv2; print(cv2.__version__)",             "OpenCV (video/image)"),
        ("yaml",      "import yaml; print(yaml.__version__)",           "PyYAML (config files)"),
        ("PIL",       "from PIL import Image; import PIL; print(PIL.__version__)", "Pillow (image saving)"),
        ("scipy",     "import scipy; print(scipy.__version__)",         "SciPy (geometry math)"),
        ("psutil",    "import psutil; print(psutil.__version__)",       "psutil (system monitor)"),
        ("ultralytics","import ultralytics; print(ultralytics.__version__)", "Ultralytics YOLO (AI detection)"),
    ]

    for module, code, label in checks:
        total += 1
        try:
            import importlib
            import importlib.metadata

            # Special handling: Pillow is installed as "Pillow" but imported as "PIL"
            if module == "PIL":
                ver = importlib.metadata.version("Pillow")
                importlib.import_module("PIL.Image")  # confirm it is importable
                print(f"  ✅  {label}: v{ver}")
                passed += 1
            else:
                lib = importlib.import_module(module)
                ver = getattr(lib, "__version__", None) or importlib.metadata.version(module)
                print(f"  ✅  {label}: v{ver}")
                passed += 1
        except importlib.metadata.PackageNotFoundError:
            print(f"  ❌  {label}: NOT INSTALLED")
            print(f"       Fix: pip install {module if module != 'PIL' else 'Pillow'}")
        except ImportError:
            print(f"  ❌  {label}: NOT INSTALLED")
            print(f"       Fix: pip install {module if module != 'PIL' else 'Pillow'}")
        except Exception as e:
            print(f"  ⚠️  {label}: Installed but warning — {e}")
            passed += 1

    print()

    # ── 3. GPU / CUDA check ──────────────────────────────────────
    print("[ GPU / CUDA ]")
    total += 1
    try:
        import torch  # type: ignore
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            print(f"  ✅  CUDA GPU available: {gpu_name}")
        else:
            print("  ℹ️  No CUDA GPU detected — will run on CPU (slower but works fine)")
        passed += 1
    except ImportError:
        # torch is installed as a dependency of ultralytics
        try:
            # pyrefly: ignore [missing-import]
            import ultralytics  # noqa: F401
            print("  ℹ️  PyTorch not imported directly (ultralytics handles it)")
            passed += 1
        except Exception:
            print("  ❌  Could not verify GPU — ultralytics may not be installed")

    print()

    # ── 4. Project structure check ───────────────────────────────
    print("[ Project Structure ]")
    required_dirs = [
        "config",
        "models",
        "data/input",
        "data/output",
        "data/evidence",
        "data/test_videos",
        "src/video",
        "src/detection",
        "src/tracking",
        "src/movement",
        "src/zones",
        "src/behavior",
        "src/events",
        "src/evidence",
        "src/output",
        "src/utils",
        "tests",
    ]

    # Script is inside border_ai_analytics/, so check relative paths from there
    script_dir = os.path.dirname(os.path.abspath(__file__))
    all_dirs_ok = True
    for d in required_dirs:
        total += 1
        full_path = os.path.join(script_dir, d)
        if os.path.isdir(full_path):
            print(f"  ✅  {d}/")
            passed += 1
        else:
            print(f"  ❌  {d}/ — MISSING")
            all_dirs_ok = False

    print()

    # ── 5. Config files ──────────────────────────────────────────
    print("[ Config Files ]")
    config_files = [
        "config/config.yaml",
        "config/cameras.yaml",
        "config/zones.yaml",
    ]
    for f in config_files:
        total += 1
        full_path = os.path.join(script_dir, f)
        if os.path.isfile(full_path):
            print(f"  ✅  {f}")
            passed += 1
        else:
            print(f"  ❌  {f} — MISSING")

    print()

    # ── Final summary ────────────────────────────────────────────
    print("=" * 60)
    print(f"  Result: {passed}/{total} checks passed")
    if passed == total:
        print()
        print("  🎉  ALL CHECKS PASSED!")
        print("  ✅  Your Phase 1 environment is ready.")
        print("  👉  Tell the AI engineer you are ready for PHASE 2.")
    else:
        failed = total - passed
        print()
        print(f"  ⚠️  {failed} check(s) failed.")
        print("  👉  Follow the ❌ fix instructions above, then re-run this script.")
    print("=" * 60)


if __name__ == "__main__":
    main()
