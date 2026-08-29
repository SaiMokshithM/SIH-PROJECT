"""
src/utils/config_loader.py
===========================
PURPOSE:
    Loads and validates the YAML configuration files.
    Provides a single place to access all settings.

HOW TO USE:
    from src.utils.config_loader import load_config, load_cameras, load_zones

    config  = load_config("config/config.yaml")
    cameras = load_cameras("config/cameras.yaml")
    zones   = load_zones("config/zones.yaml")

    conf_threshold = config["model"]["confidence_threshold"]
"""

from pathlib import Path
from typing import Any, Dict, List
import yaml

from src.utils.logger import get_logger

logger = get_logger(__name__)


def load_yaml(filepath: str) -> Dict[str, Any]:
    """
    Load a YAML file and return its contents as a dictionary.

    Args:
        filepath: Path to the .yaml file

    Returns:
        Dictionary of all settings in the file.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        yaml.YAMLError: If the file has invalid YAML syntax.
    """
    path = Path(filepath)

    if not path.exists():
        logger.error(f"Config file not found: {filepath}")
        raise FileNotFoundError(f"Config file not found: {filepath}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            logger.warning(f"Config file is empty: {filepath}")
            return {}

        logger.info(f"Config loaded: {filepath}")
        return data

    except yaml.YAMLError as e:
        logger.error(f"YAML syntax error in {filepath}: {e}")
        raise


def load_config(filepath: str = "config/config.yaml") -> Dict[str, Any]:
    """Load the main config.yaml file."""
    return load_yaml(filepath)


def load_cameras(filepath: str = "config/cameras.yaml") -> List[Dict[str, Any]]:
    """
    Load cameras.yaml and return the list of camera configurations.

    Returns:
        List of camera config dicts, e.g.:
        [{"id": "camera_001", "source": "test.mp4", "enabled": True}, ...]
    """
    data = load_yaml(filepath)
    cameras = data.get("cameras", [])

    # Only return enabled cameras
    enabled = [c for c in cameras if c.get("enabled", True)]
    disabled = [c for c in cameras if not c.get("enabled", True)]

    logger.info(f"Cameras: {len(enabled)} enabled, {len(disabled)} disabled")
    return cameras   # Return all; caller can filter by 'enabled'


def load_zones(filepath: str = "config/zones.yaml") -> List[Dict[str, Any]]:
    """
    Load zones.yaml and return the list of zone configurations.

    Returns:
        List of zone config dicts
    """
    data = load_yaml(filepath)
    zones = data.get("zones", [])
    logger.info(f"Zones loaded: {len(zones)}")
    return zones


def get_nested(config: dict, *keys, default=None):
    """
    Safely retrieve a nested value from a config dictionary.

    Example:
        fps = get_nested(config, "performance", "max_fps", default=0)

    Args:
        config:  The config dictionary
        *keys:   Sequence of keys to traverse
        default: Value to return if any key is missing

    Returns:
        The value at config[key1][key2]... or default
    """
    val = config
    for key in keys:
        if not isinstance(val, dict):
            return default
        val = val.get(key, default)
        if val is None:
            return default
    return val
