"""
src/events/event_types.py
==========================
PURPOSE:
    Central registry of all event types and their default severities.

    Every module that generates events uses these constants.
    This prevents typos like "ZONE_ENTRY" vs "ZONE_INTRUSION" spreading
    through the codebase.

HOW TO USE:
    from src.events.event_types import EventType, Severity

    event_type = EventType.RESTRICTED_ZONE_INTRUSION
    severity   = Severity.HIGH
"""

from enum import Enum


class Severity(Enum):
    """
    Operational severity levels for events.

    IMPORTANT: This is NOT a probability that something dangerous happened.
    It is an operational prioritization level — how urgently a human
    operator should review this alert.

    INFO     → Routine information (camera started, object appeared)
    LOW      → Notable but low urgency (animal movement, slow movement)
    MEDIUM   → Requires attention soon (loitering, unusual movement)
    HIGH     → Requires immediate review (zone intrusion, potential weapon)
    CRITICAL → Highest priority (multiple simultaneous high events)
    """
    INFO     = "INFO"
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    """
    All supported event types in the system.

    Using str+Enum allows direct JSON serialization (event.value = string).
    """

    # ── Movement Events ────────────────────────────────────────────────────
    STATIONARY_OBJECT       = "STATIONARY_OBJECT"
    PERSON_STATIONARY       = "PERSON_STATIONARY"
    VEHICLE_STATIONARY      = "VEHICLE_STATIONARY"
    SLOW_MOVEMENT_DETECTED  = "SLOW_MOVEMENT_DETECTED"
    FAST_MOVEMENT_DETECTED  = "FAST_MOVEMENT_DETECTED"

    # ── Object Detection Events ────────────────────────────────────────────
    PERSON_DETECTED         = "PERSON_DETECTED"
    VEHICLE_DETECTED        = "VEHICLE_DETECTED"
    ANIMAL_DETECTED         = "ANIMAL_DETECTED"

    # ── Zone Events ────────────────────────────────────────────────────────
    ZONE_ENTRY              = "ZONE_ENTRY"
    ZONE_EXIT               = "ZONE_EXIT"
    RESTRICTED_ZONE_INTRUSION = "RESTRICTED_ZONE_INTRUSION"
    HIGH_SECURITY_ZONE_INTRUSION = "HIGH_SECURITY_ZONE_INTRUSION"

    # ── Animal Zone Events ────────────────────────────────────────────────
    ANIMAL_ZONE_ENTRY       = "ANIMAL_ZONE_ENTRY"
    ANIMAL_ZONE_EXIT        = "ANIMAL_ZONE_EXIT"
    ANIMAL_MOVEMENT         = "ANIMAL_MOVEMENT"

    # ── Virtual Fence Events ──────────────────────────────────────────────
    VIRTUAL_FENCE_CROSSING  = "VIRTUAL_FENCE_CROSSING"

    # ── Behavioral Events ─────────────────────────────────────────────────
    LOITERING_DETECTED      = "LOITERING_DETECTED"
    GROUP_MOVEMENT_DETECTED = "GROUP_MOVEMENT_DETECTED"
    UNUSUAL_MOVEMENT_DETECTED = "UNUSUAL_MOVEMENT_DETECTED"
    HIGH_PERSON_DENSITY     = "HIGH_PERSON_DENSITY"

    # ── Night Events ──────────────────────────────────────────────────────
    NIGHT_MOVEMENT_DETECTED = "NIGHT_MOVEMENT_DETECTED"
    NIGHT_ZONE_INTRUSION    = "NIGHT_ZONE_INTRUSION"

    # ── Weapon Events ─────────────────────────────────────────────────────
    POTENTIAL_WEAPON_DETECTED = "POTENTIAL_WEAPON_DETECTED"

    # ── Face Events ───────────────────────────────────────────────────────
    FACE_DETECTED           = "FACE_DETECTED"

    # ── ANPR Events ───────────────────────────────────────────────────────
    LICENSE_PLATE_DETECTED  = "LICENSE_PLATE_DETECTED"

    # ── Camera Health Events ──────────────────────────────────────────────
    CAMERA_OFFLINE          = "CAMERA_OFFLINE"
    CAMERA_STREAM_ERROR     = "CAMERA_STREAM_ERROR"
    CAMERA_FRAME_FREEZE     = "CAMERA_FRAME_FREEZE"
    CAMERA_RECOVERED        = "CAMERA_RECOVERED"


# ── Default severity for each event type ──────────────────────────────────────
#
# This table is used when no custom severity is configured.
# The event engine can override these using config.yaml.

DEFAULT_SEVERITY: dict = {
    # Movement
    EventType.STATIONARY_OBJECT:            Severity.LOW,
    EventType.PERSON_STATIONARY:            Severity.LOW,
    EventType.VEHICLE_STATIONARY:           Severity.LOW,
    EventType.SLOW_MOVEMENT_DETECTED:       Severity.LOW,
    EventType.FAST_MOVEMENT_DETECTED:       Severity.MEDIUM,

    # Detection
    EventType.PERSON_DETECTED:              Severity.INFO,
    EventType.VEHICLE_DETECTED:             Severity.INFO,
    EventType.ANIMAL_DETECTED:              Severity.INFO,

    # Zones
    EventType.ZONE_ENTRY:                   Severity.LOW,
    EventType.ZONE_EXIT:                    Severity.INFO,
    EventType.RESTRICTED_ZONE_INTRUSION:    Severity.HIGH,
    EventType.HIGH_SECURITY_ZONE_INTRUSION: Severity.CRITICAL,

    # Animals
    EventType.ANIMAL_ZONE_ENTRY:            Severity.LOW,
    EventType.ANIMAL_ZONE_EXIT:             Severity.INFO,
    EventType.ANIMAL_MOVEMENT:              Severity.INFO,

    # Virtual fence
    EventType.VIRTUAL_FENCE_CROSSING:       Severity.HIGH,

    # Behavioral
    EventType.LOITERING_DETECTED:           Severity.MEDIUM,
    EventType.GROUP_MOVEMENT_DETECTED:      Severity.MEDIUM,
    EventType.UNUSUAL_MOVEMENT_DETECTED:    Severity.MEDIUM,
    EventType.HIGH_PERSON_DENSITY:          Severity.MEDIUM,

    # Night
    EventType.NIGHT_MOVEMENT_DETECTED:      Severity.MEDIUM,
    EventType.NIGHT_ZONE_INTRUSION:         Severity.HIGH,

    # Weapon
    EventType.POTENTIAL_WEAPON_DETECTED:    Severity.HIGH,

    # Face / ANPR
    EventType.FACE_DETECTED:               Severity.INFO,
    EventType.LICENSE_PLATE_DETECTED:      Severity.INFO,

    # Camera health
    EventType.CAMERA_OFFLINE:              Severity.HIGH,
    EventType.CAMERA_STREAM_ERROR:         Severity.HIGH,
    EventType.CAMERA_FRAME_FREEZE:         Severity.MEDIUM,
    EventType.CAMERA_RECOVERED:            Severity.INFO,
}


def get_default_severity(event_type: EventType) -> Severity:
    """
    Get the default operational severity for an event type.

    Args:
        event_type: EventType enum value

    Returns:
        Severity enum value (defaults to INFO if not in table)
    """
    return DEFAULT_SEVERITY.get(event_type, Severity.INFO)
