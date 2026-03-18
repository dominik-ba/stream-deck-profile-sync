"""Core synchronization logic for stream-deck-sync."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATE_FILE = ".stream-deck-sync-state.json"
PROFILES_SUBDIR = "profiles"


def _compute_file_hash(path: Path) -> str:
    """Compute the MD5 hash of a file.

    Args:
        path: Path to the file.

    Returns:
        Hex-encoded MD5 digest string.
    """
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_dir_state(directory: Path) -> dict[str, str]:
    """Compute a mapping of relative file paths to their MD5 hashes.

    Args:
        directory: Root directory to scan.

    Returns:
        Dict mapping POSIX-style relative paths to their MD5 hashes.
        Empty dict if the directory does not exist.
    """
    state: dict[str, str] = {}
    if not directory.exists():
        return state
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            rel_path = path.relative_to(directory).as_posix()
            state[rel_path] = _compute_file_hash(path)
    return state


def _load_state(sync_dir: Path) -> dict:
    """Load the sync state from the state file."""
    state_file = sync_dir / STATE_FILE
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(sync_dir: Path, state: dict) -> None:
    """Save the sync state to the state file."""
    state_file = sync_dir / STATE_FILE
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def push(profiles_dir: Path, sync_dir: Path) -> dict:
    """Push local Stream Deck profiles to the sync directory.

    Copies the entire profiles directory to ``sync_dir/profiles``, replacing
    any previously synced profiles. A state file is written to ``sync_dir``
    recording the push timestamp and file hashes.

    Args:
        profiles_dir: Path to the local Stream Deck profiles directory.
        sync_dir: Path to the shared sync directory (e.g. a cloud folder).

    Returns:
        Updated state dict containing ``last_push`` and ``profiles_state``.

    Raises:
        FileNotFoundError: If *profiles_dir* does not exist.
    """
    if not profiles_dir.exists():
        raise FileNotFoundError(
            f"Stream Deck profiles directory not found: {profiles_dir}"
        )

    sync_dir.mkdir(parents=True, exist_ok=True)
    sync_profiles_dir = sync_dir / PROFILES_SUBDIR

    # Replace any previously synced profiles with the current local ones.
    if sync_profiles_dir.exists():
        shutil.rmtree(sync_profiles_dir)
    shutil.copytree(profiles_dir, sync_profiles_dir)

    profiles_state = compute_dir_state(sync_profiles_dir)
    state = _load_state(sync_dir)
    state["last_push"] = datetime.now(timezone.utc).isoformat()
    state["profiles_state"] = profiles_state
    _save_state(sync_dir, state)

    return state


def pull(
    profiles_dir: Path,
    sync_dir: Path,
    backup: bool = True,
) -> tuple[dict, Optional[Path]]:
    """Pull Stream Deck profiles from the sync directory to the local machine.

    Replaces the local profiles directory with the profiles stored in
    ``sync_dir/profiles``. When *backup* is ``True`` a timestamped copy of
    the current local profiles is created in the same parent directory before
    any files are overwritten.

    Args:
        profiles_dir: Path to the local Stream Deck profiles directory.
        sync_dir: Path to the shared sync directory.
        backup: Create a backup of local profiles before overwriting them.

    Returns:
        Tuple of (updated state dict, backup directory path or ``None``).

    Raises:
        FileNotFoundError: If no synced profiles are found in *sync_dir*.
    """
    sync_profiles_dir = sync_dir / PROFILES_SUBDIR
    if not sync_profiles_dir.exists():
        raise FileNotFoundError(
            f"No synced profiles found in {sync_dir}. "
            "Run 'push' from another machine first."
        )

    backup_dir: Optional[Path] = None

    if backup and profiles_dir.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = profiles_dir.parent / f"ProfilesV2.backup.{timestamp}"
        shutil.copytree(profiles_dir, backup_dir)

    if profiles_dir.exists():
        shutil.rmtree(profiles_dir)
    shutil.copytree(sync_profiles_dir, profiles_dir)

    state = _load_state(sync_dir)
    state["last_pull"] = datetime.now(timezone.utc).isoformat()
    _save_state(sync_dir, state)

    return state, backup_dir


def status(profiles_dir: Path, sync_dir: Path) -> dict:
    """Compare local profiles against the synced profiles.

    Args:
        profiles_dir: Path to the local Stream Deck profiles directory.
        sync_dir: Path to the shared sync directory.

    Returns:
        Dict with the following keys:

        * ``local_only`` – files present locally but not in sync.
        * ``sync_only`` – files present in sync but not locally.
        * ``modified`` – files present in both but with different content.
        * ``in_sync`` – files identical in both locations.
        * ``last_push`` – ISO-8601 timestamp of the last push, or ``None``.
        * ``last_pull`` – ISO-8601 timestamp of the last pull, or ``None``.
        * ``has_local`` – whether the local profiles directory exists.
        * ``has_sync`` – whether synced profiles exist in *sync_dir*.
    """
    local_state = compute_dir_state(profiles_dir)
    sync_profiles_dir = sync_dir / PROFILES_SUBDIR
    sync_state = compute_dir_state(sync_profiles_dir)

    local_keys = set(local_state.keys())
    sync_keys = set(sync_state.keys())

    local_only = sorted(local_keys - sync_keys)
    sync_only = sorted(sync_keys - local_keys)
    modified = sorted(
        k for k in local_keys & sync_keys if local_state[k] != sync_state[k]
    )
    in_sync = sorted(
        k for k in local_keys & sync_keys if local_state[k] == sync_state[k]
    )

    metadata = _load_state(sync_dir)

    return {
        "local_only": local_only,
        "sync_only": sync_only,
        "modified": modified,
        "in_sync": in_sync,
        "last_push": metadata.get("last_push"),
        "last_pull": metadata.get("last_pull"),
        "has_local": profiles_dir.exists(),
        "has_sync": sync_profiles_dir.exists(),
    }
