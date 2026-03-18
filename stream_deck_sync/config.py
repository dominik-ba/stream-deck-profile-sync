"""Configuration management for stream-deck-sync."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".stream-deck-sync"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Load configuration from the config file.

    Returns:
        Configuration dict. Empty dict if the config file does not exist.
    """
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    """Save configuration to the config file.

    Creates the config directory if it does not exist.

    Args:
        config: Configuration dict to persist.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_sync_dir() -> Optional[Path]:
    """Return the configured sync directory, or None if not set.

    Returns:
        Path to the sync directory, or None if not configured.
    """
    config = load_config()
    sync_dir = config.get("sync_dir")
    if sync_dir:
        return Path(sync_dir)
    return None


def set_sync_dir(sync_dir: Path) -> None:
    """Persist the sync directory to the config file.

    Args:
        sync_dir: Path to the sync directory to save.
    """
    config = load_config()
    config["sync_dir"] = str(sync_dir)
    save_config(config)
