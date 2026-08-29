"""
src/detection/detection_result.py
==================================
PURPOSE:
    Defines the DetectionResult class — a clean container that holds
    everything about ONE detected object in ONE frame.

    Think of it like a "detection record card" that gets passed between
    all the modules (tracker, movement analyzer, zone checker, etc.)

WHY A SEPARATE CLASS?
    If we just passed raw YOLO output around, every module would need
    to understand YOLO's internal format. Instead, we convert YOLO output
    ONCE into our own clean format, and every module uses that.

WHAT IT CONTAINS:
    - class_name:  "person", "car", "dog", etc.
    - class_id:    integer ID (0=person, 2=car, etc. from COCO dataset)
    - confidence:  how sure the model is (0.0 to 1.0)
    - bbox:        [x1, y1, x2, y2] pixel coordinates of the box
    - center:      [cx, cy] center point of the box
    - frame_number: which frame this came from
    - timestamp:   when this was detected
    - camera_id:   which camera produced this
    - category:    broad category ("person", "vehicle", "animal", "other")
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time


# ── COCO Class Definitions ────────────────────────────────────────────────────
#
# YOLOv8 pretrained on COCO dataset knows 80 classes.
# We define which classes belong to which category.
# Full COCO class list: https://docs.ultralytics.com/datasets/detect/coco/

# Classes we want to detect and their COCO IDs
PERSON_CLASSES = {
    0: "person",
}

VEHICLE_CLASSES = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Animals available in the COCO pretrained model
ANIMAL_CLASSES = {
    14: "bird",
    15: "cat",
    16: "dog",
    17: "horse",
    18: "sheep",
    19: "cow",
    20: "elephant",
    21: "bear",
    22: "zebra",
    23: "giraffe",
}

WEAPON_CLASSES = {
    43: "knife",
    76: "scissors",
}

# Combined lookup: class_id → class_name (for all classes we care about)
ALL_TARGET_CLASSES = {
    **PERSON_CLASSES,
    **VEHICLE_CLASSES,
    **ANIMAL_CLASSES,
    **WEAPON_CLASSES,
}

# Reverse lookup: class_name → class_id
CLASS_NAME_TO_ID = {v: k for k, v in ALL_TARGET_CLASSES.items()}


def get_category(class_id: int) -> str:
    """
    Determine the broad category of a detected object.

    Args:
        class_id: COCO class integer ID

    Returns:
        "person", "vehicle", "animal", "weapon", or "other"
    """
    if class_id in PERSON_CLASSES:
        return "person"
    elif class_id in VEHICLE_CLASSES:
        return "vehicle"
    elif class_id in ANIMAL_CLASSES:
        return "animal"
    elif class_id in WEAPON_CLASSES:
        return "weapon"
    else:
        return "other"


# ── Colors for visualization (BGR format for OpenCV) ─────────────────────────
#
# BGR = Blue, Green, Red (OpenCV uses this order, NOT RGB)
# Example: (0, 255, 0) = pure green

CATEGORY_COLORS = {
    "person":  (0, 255, 0),      # Green
    "vehicle": (0, 0, 255),      # Red
    "animal":  (255, 165, 0),    # Orange
    "weapon":  (0, 0, 255),      # Red
    "plate":   (255, 255, 0),    # Cyan/Yellow
    "other":   (200, 200, 200),  # Gray
}

CLASS_COLORS = {
    # Person
    0:  (0, 255, 0),      # person → Green
    # Vehicles
    1:  (100, 200, 255),  # bicycle → Light Blue
    2:  (0, 0, 255),      # car → Red
    3:  (255, 0, 255),    # motorcycle → Magenta
    5:  (128, 0, 255),    # bus → Purple
    7:  (0, 100, 255),    # truck → Dark Orange
    # Animals
    14: (255, 200, 0),    # bird → Yellow
    15: (0, 165, 255),    # cat → Orange
    16: (30, 105, 210),   # dog → Brown
    17: (0, 255, 255),    # horse → Cyan
    18: (200, 100, 50),   # sheep → Teal
    19: (50, 200, 100),   # cow → Green-ish
    20: (180, 100, 200),  # elephant → Purple-ish
    21: (50, 50, 200),    # bear → Dark Red
    22: (200, 200, 50),   # zebra → Olive
    23: (100, 200, 200),  # giraffe → Light Teal
    # Weapons
    43: (0, 0, 255),      # knife → Bright Red
    76: (0, 100, 255),    # scissors → Red/Orange
}


@dataclass
class DetectionResult:
    """
    A single detected object in a single frame.

    This is our standard "detection record" — every part of the system
    reads detections in this format.

    Attributes:
        class_name:    Human-readable name, e.g. "person", "car", "dog"
        class_id:      Integer COCO class ID
        confidence:    Detection confidence score (0.0 to 1.0)
        bbox:          Bounding box [x1, y1, x2, y2] in pixels
        center:        Center point [cx, cy] computed from bbox
        category:      Broad category: "person", "vehicle", "animal", "other"
        frame_number:  Frame index in the video
        timestamp:     Unix timestamp when detected
        camera_id:     ID of the camera that produced this frame
        color:         BGR color for visualization
    """

    class_name: str
    class_id: int
    confidence: float
    bbox: List[int]           # [x1, y1, x2, y2]
    center: List[int]         # [cx, cy]
    category: str
    frame_number: int = 0
    timestamp: float = field(default_factory=time.time)
    camera_id: str = "camera_001"
    color: tuple = field(default_factory=lambda: (0, 255, 0))

    @property
    def x1(self) -> int:
        return self.bbox[0]

    @property
    def y1(self) -> int:
        return self.bbox[1]

    @property
    def x2(self) -> int:
        return self.bbox[2]

    @property
    def y2(self) -> int:
        return self.bbox[3]

    @property
    def width(self) -> int:
        """Width of the bounding box in pixels."""
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        """Height of the bounding box in pixels."""
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> int:
        """Area of the bounding box in pixels squared."""
        return self.width * self.height

    def to_dict(self) -> dict:
        """
        Convert to a dictionary for JSON serialization.

        Returns:
            dict: All detection fields as a plain dictionary
        """
        return {
            "class_name":   self.class_name,
            "class_id":     self.class_id,
            "confidence":   round(self.confidence, 4),
            "bbox":         self.bbox,
            "center":       self.center,
            "category":     self.category,
            "frame_number": self.frame_number,
            "timestamp":    self.timestamp,
            "camera_id":    self.camera_id,
            "bbox_width":   self.width,
            "bbox_height":  self.height,
        }

    def __repr__(self) -> str:
        return (
            f"DetectionResult("
            f"class={self.class_name!r}, "
            f"conf={self.confidence:.2f}, "
            f"bbox={self.bbox}, "
            f"category={self.category!r})"
        )


def make_detection(
    class_id: int,
    confidence: float,
    bbox: List[int],
    frame_number: int = 0,
    camera_id: str = "camera_001",
) -> Optional["DetectionResult"]:
    """
    Factory function: create a DetectionResult from raw YOLO output.

    Returns None if the class_id is not in our target list.

    Args:
        class_id:     COCO integer class ID
        confidence:   Model confidence (0.0–1.0)
        bbox:         [x1, y1, x2, y2] pixel coordinates
        frame_number: Frame index in the video
        camera_id:    Camera identifier string

    Returns:
        DetectionResult or None
    """
    if class_id not in ALL_TARGET_CLASSES:
        return None

    class_name = ALL_TARGET_CLASSES[class_id]
    category = get_category(class_id)
    color = CLASS_COLORS.get(class_id, (200, 200, 200))

    # Calculate center point from bounding box
    cx = (bbox[0] + bbox[2]) // 2
    cy = (bbox[1] + bbox[3]) // 2

    return DetectionResult(
        class_name=class_name,
        class_id=class_id,
        confidence=confidence,
        bbox=bbox,
        center=[cx, cy],
        category=category,
        frame_number=frame_number,
        camera_id=camera_id,
        color=color,
    )
