"""
src/utils/logger.py — Centralized Logging Setup
================================================
PURPOSE:
    Every module in our system uses this logger instead of print().
    Benefits:
    - Shows timestamp, severity level, and which module logged it
    - Can write to both console AND a log file simultaneously
    - Log level is controlled from config.yaml (DEBUG/INFO/WARNING/ERROR)
    - Rotating file handler prevents log files from growing forever

USAGE (in any other module):
    from src.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Camera connected")
    logger.warning("Low confidence detection")
    logger.error("Failed to open video file")
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path


# Global registry so we don't create duplicate handlers
_loggers: dict[str, logging.Logger] = {}


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = True,
    log_file: str = "data/output/engine.log",
    max_log_size_mb: int = 10,
    backup_count: int = 3,
) -> None:
    """
    Call this ONCE at application startup (from main.py).

    Args:
        level:           Log verbosity — "DEBUG", "INFO", "WARNING", "ERROR"
        log_to_file:     If True, also write logs to a file
        log_file:        Path to the log file
        max_log_size_mb: Rotate log when it reaches this size
        backup_count:    How many old log files to keep
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # ── Format: time | level | module | message ──────────────────
    fmt = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=date_fmt)

    # ── Root logger ───────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any existing handlers (avoids duplicates on re-init)
    root.handlers.clear()

    # ── Console handler ───────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # ── File handler (optional) ───────────────────────────────────
    if log_to_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_log_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Silence noisy third-party libraries
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger for a module.

    Args:
        name: Typically pass __name__ from the calling module.

    Returns:
        A configured Logger instance.

    Example:
        logger = get_logger(__name__)
        logger.info("Module initialized")
    """
    return logging.getLogger(name)
