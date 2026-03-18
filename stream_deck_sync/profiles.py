"""Stream Deck profile location detection for supported platforms."""

from __future__ import annotations

import os
import platform
from pathlib import Path


def get_profiles_dir() -> Path:
    """Return the Stream Deck profiles directory for the current platform.

    Returns:
        Path to the Stream Deck ProfilesV2 directory.

    Raises:
        RuntimeError: If the current platform is not supported or the
            required environment variable is missing.
    """
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError(
                "APPDATA environment variable is not set. "
                "Cannot determine the Stream Deck profiles directory."
            )
        return Path(appdata) / "Elgato" / "StreamDeck" / "ProfilesV2"
    elif system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "com.elgato.StreamDeck"
            / "ProfilesV2"
        )
    else:
        raise RuntimeError(
            f"Unsupported platform: {system}. "
            "Stream Deck software is only available on Windows and macOS."
        )


def get_plugins_dir() -> Path:
    """Return the Stream Deck plugins directory for the current platform.

    Returns:
        Path to the Stream Deck Plugins directory.

    Raises:
        RuntimeError: If the current platform is not supported or the
            required environment variable is missing.
    """
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError(
                "APPDATA environment variable is not set. "
                "Cannot determine the Stream Deck plugins directory."
            )
        return Path(appdata) / "Elgato" / "StreamDeck" / "Plugins"
    elif system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "com.elgato.StreamDeck"
            / "Plugins"
        )
    else:
        raise RuntimeError(
            f"Unsupported platform: {system}. "
            "Stream Deck software is only available on Windows and macOS."
        )
