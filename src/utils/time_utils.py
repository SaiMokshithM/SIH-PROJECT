"""
src/utils/time_utils.py — Timestamp & Time Utilities
=====================================================
PURPOSE:
    Provides consistent timestamp formatting across the entire engine.
    All timestamps use ISO 8601 format so the Spring Boot backend
    can parse them without ambiguity.

    ISO 8601 example: "2026-08-29T18:30:25.123456"

USAGE:
    from src.utils.time_utils import now_iso, now_ts, format_duration
    ts = now_iso()           # "2026-08-29T18:30:25.123456"
    elapsed = elapsed_seconds(start_time)
"""

import time
from datetime import datetime, timezone


def now_iso() -> str:
    """
    Return the current local time as an ISO 8601 string.

    Returns:
        str: e.g. "2026-08-29T18:30:25.123456"
    """
    return datetime.now().isoformat()


def now_utc_iso() -> str:
    """
    Return the current UTC time as an ISO 8601 string with Z suffix.

    Returns:
        str: e.g. "2026-08-29T13:00:25.123456+00:00"
    """
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> float:
    """
    Return the current Unix timestamp (seconds since epoch).
    Used internally for duration calculations.

    Returns:
        float: e.g. 1724946025.123
    """
    return time.time()


def elapsed_seconds(start_timestamp: float) -> float:
    """
    Calculate how many seconds have passed since start_timestamp.

    Args:
        start_timestamp: A value previously returned by now_ts()

    Returns:
        float: Number of seconds elapsed (e.g. 12.5)

    Example:
        start = now_ts()
        # ... do something ...
        duration = elapsed_seconds(start)
        print(f"Took {duration:.2f} seconds")
    """
    return time.time() - start_timestamp


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds into a human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        str: e.g. "2m 30s" or "45s" or "1h 5m 20s"

    Example:
        format_duration(150)   → "2m 30s"
        format_duration(45)    → "45s"
        format_duration(3720)  → "1h 2m 0s"
    """
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def date_folder_name() -> str:
    """
    Return today's date as a folder-safe string.
    Used for organizing evidence by date.

    Returns:
        str: e.g. "2026-08-29"
    """
    return datetime.now().strftime("%Y-%m-%d")


def time_str_for_filename() -> str:
    """
    Return current time formatted for use in filenames (no colons).

    Returns:
        str: e.g. "18-30-25"
    """
    return datetime.now().strftime("%H-%M-%S")
