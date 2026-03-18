"""Core synchronization logic for stream-deck-sync."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATE_FILE = ".stream-deck-sync-state.json"
PROFILES_SUBDIR = "profiles"
PLUGINS_SUBDIR = "plugins"

# File name patterns that are excluded from syncing and status comparisons by
# default.  These files are written by Stream Deck plugins at runtime and
# should not be tracked across machines.
DEFAULT_EXCLUDE_PATTERNS: list[str] = ["*.log"]


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


def compute_dir_state(
    directory: Path,
    exclude_patterns: Optional[list[str]] = None,
) -> dict[str, str]:
    """Compute a mapping of relative file paths to their MD5 hashes.

    Args:
        directory: Root directory to scan.
        exclude_patterns: List of ``fnmatch``-style filename patterns to skip
            (e.g. ``["*.log"]``).  When ``None``, :data:`DEFAULT_EXCLUDE_PATTERNS`
            is used.  Pass an empty list to disable all exclusions.

    Returns:
        Dict mapping POSIX-style relative paths to their MD5 hashes.
        Empty dict if the directory does not exist.
    """
    if exclude_patterns is None:
        exclude_patterns = DEFAULT_EXCLUDE_PATTERNS
    state: dict[str, str] = {}
    if not directory.exists():
        return state
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            if any(fnmatch.fnmatch(path.name, p) for p in exclude_patterns):
                continue
            rel_path = path.relative_to(directory).as_posix()
            state[rel_path] = _compute_file_hash(path)
    return state


def read_manifest_name(base_dir: Path, folder_name: str) -> str:
    """Read the human-readable display name from a Stream Deck manifest.json.

    Looks for ``base_dir/folder_name/manifest.json`` and returns the value of
    the ``Name`` field.  Falls back to *folder_name* when the file is missing,
    unreadable, or contains no ``Name`` key.

    Args:
        base_dir: Directory that contains the profile or plugin folder.
        folder_name: Name of the individual ``.sdProfile`` or ``.sdPlugin``
            sub-directory.

    Returns:
        Human-readable display name, or *folder_name* as a fallback.
    """
    manifest = base_dir / folder_name / "manifest.json"
    if manifest.exists():
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("Name")
            if name:
                return str(name)
        except (json.JSONDecodeError, OSError):
            pass
    return folder_name


def _group_by_top_dir(file_paths: list[str]) -> dict[str, list[str]]:
    """Group POSIX-style relative file paths by their first path component.

    Args:
        file_paths: List of POSIX relative paths (e.g. ``"ABC.sdProfile/page.json"``).

    Returns:
        Ordered dict mapping the top-level directory name to a list of the
        remaining path segments for each file in that directory.
    """
    groups: dict[str, list[str]] = {}
    for path in file_paths:
        parts = Path(path).parts
        top_dir = parts[0] if parts else path
        remainder = "/".join(parts[1:]) if len(parts) > 1 else ""
        groups.setdefault(top_dir, []).append(remainder)
    return groups


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


def push(
    profiles_dir: Path,
    sync_dir: Path,
    plugins_dir: Optional[Path] = None,
    exclude_patterns: Optional[list[str]] = None,
) -> dict:
    """Push local Stream Deck profiles (and optionally plugins) to the sync directory.

    Copies the entire profiles directory to ``sync_dir/profiles``, replacing
    any previously synced profiles.  When *plugins_dir* is provided and
    exists, the plugins directory is also copied to ``sync_dir/plugins``.
    A state file is written to ``sync_dir`` recording the push timestamp and
    file hashes.

    Files whose names match any pattern in *exclude_patterns* are not copied
    to the sync directory and are not tracked in the state.

    Args:
        profiles_dir: Path to the local Stream Deck profiles directory.
        sync_dir: Path to the shared sync directory (e.g. a cloud folder).
        plugins_dir: Path to the local Stream Deck plugins directory.  When
            supplied, plugins are included in the push.
        exclude_patterns: List of ``fnmatch``-style filename patterns to skip
            (e.g. ``["*.log"]``).  When ``None``, :data:`DEFAULT_EXCLUDE_PATTERNS`
            is used.  Pass an empty list to disable all exclusions.

    Returns:
        Updated state dict containing ``last_push``, ``profiles_state``, and
        optionally ``plugins_state``.

    Raises:
        FileNotFoundError: If *profiles_dir* does not exist.
    """
    if exclude_patterns is None:
        exclude_patterns = DEFAULT_EXCLUDE_PATTERNS

    if not profiles_dir.exists():
        raise FileNotFoundError(
            f"Stream Deck profiles directory not found: {profiles_dir}"
        )

    sync_dir.mkdir(parents=True, exist_ok=True)
    sync_profiles_dir = sync_dir / PROFILES_SUBDIR

    # Replace any previously synced profiles with the current local ones.
    if sync_profiles_dir.exists():
        shutil.rmtree(sync_profiles_dir)
    _ignore = shutil.ignore_patterns(*exclude_patterns) if exclude_patterns is not None else None
    shutil.copytree(profiles_dir, sync_profiles_dir, ignore=_ignore)

    profiles_state = compute_dir_state(sync_profiles_dir, exclude_patterns=exclude_patterns)
    state = _load_state(sync_dir)
    state["last_push"] = datetime.now(timezone.utc).isoformat()
    state["profiles_state"] = profiles_state

    if plugins_dir is not None and plugins_dir.exists():
        sync_plugins_dir = sync_dir / PLUGINS_SUBDIR
        if sync_plugins_dir.exists():
            shutil.rmtree(sync_plugins_dir)
        shutil.copytree(plugins_dir, sync_plugins_dir, ignore=_ignore)
        state["plugins_state"] = compute_dir_state(
            sync_plugins_dir, exclude_patterns=exclude_patterns
        )

    _save_state(sync_dir, state)

    return state


def pull(
    profiles_dir: Path,
    sync_dir: Path,
    backup: bool = True,
    plugins_dir: Optional[Path] = None,
) -> tuple[dict, Optional[Path], Optional[Path]]:
    """Pull Stream Deck profiles (and optionally plugins) from the sync directory.

    Replaces the local profiles directory with the profiles stored in
    ``sync_dir/profiles``.  When *plugins_dir* is provided, the local plugins
    directory is also replaced from ``sync_dir/plugins`` (if that directory
    exists in the sync folder).

    When *backup* is ``True`` timestamped copies of the current local
    directories are created before any files are overwritten.

    Args:
        profiles_dir: Path to the local Stream Deck profiles directory.
        sync_dir: Path to the shared sync directory.
        backup: Create a backup of local data before overwriting.
        plugins_dir: Path to the local Stream Deck plugins directory.  When
            supplied, plugins are included in the pull.

    Returns:
        Tuple of ``(state, profiles_backup_dir, plugins_backup_dir)``.
        Each backup path is ``None`` when no backup was created.

    Raises:
        FileNotFoundError: If no synced profiles are found in *sync_dir*.
    """
    sync_profiles_dir = sync_dir / PROFILES_SUBDIR
    if not sync_profiles_dir.exists():
        raise FileNotFoundError(
            f"No synced profiles found in {sync_dir}. "
            "Run 'push' from another machine first."
        )

    profiles_backup_dir: Optional[Path] = None

    if backup and profiles_dir.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        profiles_backup_dir = profiles_dir.parent / f"ProfilesV2.backup.{timestamp}"
        shutil.copytree(profiles_dir, profiles_backup_dir)

    if profiles_dir.exists():
        shutil.rmtree(profiles_dir)
    shutil.copytree(sync_profiles_dir, profiles_dir)

    plugins_backup_dir: Optional[Path] = None

    if plugins_dir is not None:
        sync_plugins_dir = sync_dir / PLUGINS_SUBDIR
        if sync_plugins_dir.exists():
            if backup and plugins_dir.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                plugins_backup_dir = (
                    plugins_dir.parent / f"Plugins.backup.{timestamp}"
                )
                shutil.copytree(plugins_dir, plugins_backup_dir)
            if plugins_dir.exists():
                shutil.rmtree(plugins_dir)
            shutil.copytree(sync_plugins_dir, plugins_dir)

    state = _load_state(sync_dir)
    state["last_pull"] = datetime.now(timezone.utc).isoformat()
    _save_state(sync_dir, state)

    return state, profiles_backup_dir, plugins_backup_dir


def status(
    profiles_dir: Path,
    sync_dir: Path,
    plugins_dir: Optional[Path] = None,
    exclude_patterns: Optional[list[str]] = None,
) -> dict:
    """Compare local profiles (and optionally plugins) against the synced copies.

    Args:
        profiles_dir: Path to the local Stream Deck profiles directory.
        sync_dir: Path to the shared sync directory.
        plugins_dir: Path to the local Stream Deck plugins directory.  When
            supplied, plugins are also compared.
        exclude_patterns: List of ``fnmatch``-style filename patterns to ignore
            during comparison (e.g. ``["*.log"]``).  When ``None``,
            :data:`DEFAULT_EXCLUDE_PATTERNS` is used.  Pass an empty list to
            disable all exclusions.

    Returns:
        Dict with the following keys:

        Profiles section:

        * ``local_only`` – profile files present locally but not in sync.
        * ``sync_only`` – profile files present in sync but not locally.
        * ``modified`` – profile files present in both but with different content.
        * ``in_sync`` – profile files identical in both locations.
        * ``has_local`` – whether the local profiles directory exists.
        * ``has_sync`` – whether synced profiles exist in *sync_dir*.

        Plugins section (populated only when *plugins_dir* is given):

        * ``plugins_local_only`` – plugin files present locally but not in sync.
        * ``plugins_sync_only`` – plugin files present in sync but not locally.
        * ``plugins_modified`` – plugin files present in both but with different content.
        * ``plugins_in_sync`` – plugin files identical in both locations.
        * ``has_local_plugins`` – whether the local plugins directory exists.
        * ``has_sync_plugins`` – whether synced plugins exist in *sync_dir*.

        Metadata:

        * ``last_push`` – ISO-8601 timestamp of the last push, or ``None``.
        * ``last_pull`` – ISO-8601 timestamp of the last pull, or ``None``.
    """
    local_state = compute_dir_state(profiles_dir, exclude_patterns=exclude_patterns)
    sync_profiles_dir = sync_dir / PROFILES_SUBDIR
    sync_state = compute_dir_state(sync_profiles_dir, exclude_patterns=exclude_patterns)

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

    result: dict = {
        "local_only": local_only,
        "sync_only": sync_only,
        "modified": modified,
        "in_sync": in_sync,
        "has_local": profiles_dir.exists(),
        "has_sync": sync_profiles_dir.exists(),
        "plugins_local_only": [],
        "plugins_sync_only": [],
        "plugins_modified": [],
        "plugins_in_sync": [],
        "has_local_plugins": False,
        "has_sync_plugins": False,
        "last_push": metadata.get("last_push"),
        "last_pull": metadata.get("last_pull"),
    }

    if plugins_dir is not None:
        sync_plugins_dir = sync_dir / PLUGINS_SUBDIR
        local_plugins = compute_dir_state(plugins_dir, exclude_patterns=exclude_patterns)
        sync_plugins = compute_dir_state(sync_plugins_dir, exclude_patterns=exclude_patterns)

        lp_keys = set(local_plugins.keys())
        sp_keys = set(sync_plugins.keys())

        result["plugins_local_only"] = sorted(lp_keys - sp_keys)
        result["plugins_sync_only"] = sorted(sp_keys - lp_keys)
        result["plugins_modified"] = sorted(
            k for k in lp_keys & sp_keys if local_plugins[k] != sync_plugins[k]
        )
        result["plugins_in_sync"] = sorted(
            k for k in lp_keys & sp_keys if local_plugins[k] == sync_plugins[k]
        )
        result["has_local_plugins"] = plugins_dir.exists()
        result["has_sync_plugins"] = sync_plugins_dir.exists()

    return result
