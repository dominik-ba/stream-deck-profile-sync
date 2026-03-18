"""Schedule-based automatic sync for stream-deck-sync.

Registers a recurring OS-level task (macOS launchd / Windows Task Scheduler)
that calls ``stream-deck-sync push`` or ``stream-deck-sync pull`` at a
configurable interval.  The two platforms use completely different scheduling
APIs, but the public interface is the same on both.

macOS
-----
A *Launch Agent* plist is written to ``~/Library/LaunchAgents/`` and loaded
with ``launchctl``.  The agent runs as the current user and logs to
``~/Library/Logs/stream-deck-sync.log``.

Windows
-------
A scheduled task is created with the built-in ``schtasks.exe`` utility and
runs under the current user's session.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional

# ----- Platform identifiers ---------------------------------------------------

LAUNCH_AGENT_ID = "com.stream-deck-sync.autosync"
WINDOWS_TASK_NAME = "StreamDeckProfileSync"

# ----- Public API -------------------------------------------------------------


def enable_schedule(
    interval_minutes: int,
    action: str,
    sync_dir: Optional[Path] = None,
    profiles_dir: Optional[Path] = None,
    plugins_dir: Optional[Path] = None,
    no_plugins: bool = False,
) -> None:
    """Register a recurring OS task that runs ``push`` or ``pull``.

    Any previously registered schedule for stream-deck-sync is replaced.

    Args:
        interval_minutes: How often the sync should run, in minutes.
        action: Either ``"push"`` or ``"pull"``.
        sync_dir: Override the configured sync directory.
        profiles_dir: Override the auto-detected profiles directory.
        plugins_dir: Override the auto-detected plugins directory.
        no_plugins: When ``True``, ``--no-plugins`` is forwarded to the
            scheduled command.

    Raises:
        RuntimeError: On platforms other than macOS and Windows.
        subprocess.CalledProcessError: When the OS command to register the
            task fails.
    """
    if action not in ("push", "pull"):
        raise ValueError(f"action must be 'push' or 'pull', got: {action!r}")

    if sys.platform == "darwin":
        _enable_schedule_macos(
            interval_minutes, action, sync_dir, profiles_dir, plugins_dir, no_plugins
        )
    elif sys.platform == "win32":
        _enable_schedule_windows(
            interval_minutes, action, sync_dir, profiles_dir, plugins_dir, no_plugins
        )
    else:
        raise RuntimeError(
            "Scheduled sync is only supported on macOS and Windows."
        )


def disable_schedule() -> None:
    """Remove the registered OS task for stream-deck-sync.

    Raises:
        RuntimeError: When no schedule is currently configured, or on an
            unsupported platform.
        subprocess.CalledProcessError: When the OS command to remove the
            task fails.
    """
    if sys.platform == "darwin":
        _disable_schedule_macos()
    elif sys.platform == "win32":
        _disable_schedule_windows()
    else:
        raise RuntimeError(
            "Scheduled sync is only supported on macOS and Windows."
        )


def get_schedule_status() -> dict:
    """Return the current schedule configuration.

    Returns:
        A dict with at least an ``"enabled"`` boolean key.  When enabled,
        also contains ``"action"`` (``"push"`` or ``"pull"``) and
        ``"interval_minutes"`` (int).
    """
    if sys.platform == "darwin":
        return _get_status_macos()
    elif sys.platform == "win32":
        return _get_status_windows()
    else:
        return {"enabled": False}


# ----- Command-line argument builder ------------------------------------------


def _build_command_args(
    action: str,
    sync_dir: Optional[Path],
    profiles_dir: Optional[Path],
    plugins_dir: Optional[Path],
    no_plugins: bool,
) -> list[str]:
    """Build the argv list for the scheduled stream-deck-sync invocation.

    Uses the same Python interpreter that is currently running so the correct
    virtual-environment / installation is always targeted.

    Args:
        action: ``"push"`` or ``"pull"``.
        sync_dir: Optional sync directory override.
        profiles_dir: Optional profiles directory override.
        plugins_dir: Optional plugins directory override.
        no_plugins: Whether to append ``--no-plugins``.

    Returns:
        List of strings suitable for use as ``ProgramArguments`` in a plist
        or as the command for ``schtasks /TR``.
    """
    args: list[str] = [sys.executable, "-m", "stream_deck_sync", action]
    if sync_dir is not None:
        args.extend(["--sync-dir", str(sync_dir)])
    if profiles_dir is not None:
        args.extend(["--profiles-dir", str(profiles_dir)])
    if plugins_dir is not None:
        args.extend(["--plugins-dir", str(plugins_dir)])
    if no_plugins:
        args.append("--no-plugins")
    # Pull in scheduled mode should never create backups to keep it quiet.
    if action == "pull":
        args.append("--no-backup")
    return args


# ----- macOS (launchd) --------------------------------------------------------


def _get_plist_path() -> Path:
    """Return the path to the Launch Agent plist file."""
    return (
        Path.home()
        / "Library"
        / "LaunchAgents"
        / f"{LAUNCH_AGENT_ID}.plist"
    )


def _build_plist(args: list[str], interval_minutes: int) -> bytes:
    """Serialise a launchd plist as bytes.

    Args:
        args: Full argv list for the scheduled program.
        interval_minutes: Run interval in minutes.

    Returns:
        Plist XML encoded as UTF-8 bytes.
    """
    log_path = str(Path.home() / "Library" / "Logs" / "stream-deck-sync.log")
    data = {
        "Label": LAUNCH_AGENT_ID,
        "ProgramArguments": args,
        "StartInterval": interval_minutes * 60,
        "RunAtLoad": False,
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
    }
    return plistlib.dumps(data, fmt=plistlib.FMT_XML)


def _enable_schedule_macos(
    interval_minutes: int,
    action: str,
    sync_dir: Optional[Path],
    profiles_dir: Optional[Path],
    plugins_dir: Optional[Path],
    no_plugins: bool,
) -> None:
    """Register or update the Launch Agent on macOS."""
    args = _build_command_args(
        action, sync_dir, profiles_dir, plugins_dir, no_plugins
    )
    plist_bytes = _build_plist(args, interval_minutes)

    plist_path = _get_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    # Unload any currently registered agent before replacing the plist.
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            check=False,
            capture_output=True,
        )

    plist_path.write_bytes(plist_bytes)

    subprocess.run(
        ["launchctl", "load", str(plist_path)],
        check=True,
        capture_output=True,
    )


def _disable_schedule_macos() -> None:
    """Unload and remove the Launch Agent on macOS."""
    plist_path = _get_plist_path()
    if not plist_path.exists():
        raise RuntimeError(
            "No stream-deck-sync schedule is currently configured."
        )
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        check=True,
        capture_output=True,
    )
    plist_path.unlink()


def _get_status_macos() -> dict:
    """Read schedule status from the plist file on macOS."""
    plist_path = _get_plist_path()
    if not plist_path.exists():
        return {"enabled": False}

    try:
        with open(plist_path, "rb") as fh:
            data = plistlib.load(fh)
        prog_args: list[str] = data.get("ProgramArguments", [])
        # argv is: [python, "-m", "stream_deck_sync", action, ...]
        action = prog_args[3] if len(prog_args) > 3 else "unknown"
        interval_seconds: int = data.get("StartInterval", 0)
        return {
            "enabled": True,
            "action": action,
            "interval_minutes": interval_seconds // 60,
        }
    except Exception:
        return {"enabled": True}


# ----- Windows (Task Scheduler) -----------------------------------------------

_SCHTASKS = "schtasks"


def _enable_schedule_windows(
    interval_minutes: int,
    action: str,
    sync_dir: Optional[Path],
    profiles_dir: Optional[Path],
    plugins_dir: Optional[Path],
    no_plugins: bool,
) -> None:
    """Create or replace the scheduled task on Windows."""
    args = _build_command_args(
        action, sync_dir, profiles_dir, plugins_dir, no_plugins
    )
    # Quote arguments that contain spaces.
    quoted_args = [f'"{a}"' if " " in a else a for a in args]
    command = " ".join(quoted_args)

    # Remove any existing task silently.
    subprocess.run(
        [_SCHTASKS, "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"],
        check=False,
        capture_output=True,
    )

    subprocess.run(
        [
            _SCHTASKS,
            "/Create",
            "/TN",
            WINDOWS_TASK_NAME,
            "/TR",
            command,
            "/SC",
            "MINUTE",
            "/MO",
            str(interval_minutes),
            "/F",
        ],
        check=True,
        capture_output=True,
    )


def _disable_schedule_windows() -> None:
    """Delete the scheduled task on Windows."""
    result = subprocess.run(
        [_SCHTASKS, "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "No stream-deck-sync schedule is currently configured."
        )


def _get_status_windows() -> dict:
    """Query Task Scheduler for the stream-deck-sync task status on Windows."""
    result = subprocess.run(
        [_SCHTASKS, "/Query", "/TN", WINDOWS_TASK_NAME, "/FO", "CSV", "/NH"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {"enabled": False}
    return {"enabled": True}


# ----- Convenience helpers for human-readable output -------------------------


def describe_schedule(status: dict) -> str:
    """Return a single human-readable line describing the schedule status.

    Args:
        status: Dict returned by :func:`get_schedule_status`.

    Returns:
        A short description string.
    """
    if not status.get("enabled"):
        return "No schedule configured."
    action = status.get("action", "unknown")
    interval = status.get("interval_minutes", "?")
    return (
        f"Scheduled {action} every {interval} minute(s)."
    )


def _plist_comment() -> str:
    """Return an informational comment block for the generated plist."""
    return textwrap.dedent(
        """\
        <!-- Generated by stream-deck-sync.
             To edit the schedule, run: stream-deck-sync schedule enable ...
             To remove the schedule, run: stream-deck-sync schedule disable
        -->"""
    )
