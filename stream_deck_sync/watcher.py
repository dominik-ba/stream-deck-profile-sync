"""File-watching automatic sync for stream-deck-sync.

Monitors the local profiles / plugins directories and the cloud sync directory
using the ``watchdog`` library and triggers ``push`` or ``pull`` automatically
when relevant changes are detected.

Usage
-----
Install the optional dependency first::

    pip install "stream-deck-profile-sync[watch]"

Then start watching::

    stream-deck-sync watch            # push on local changes, pull on sync changes
    stream-deck-sync watch --push-only
    stream-deck-sync watch --pull-only

The watcher runs in the foreground and can be stopped with **Ctrl-C**.  To run
it in the background use your OS's standard tools (e.g. ``nohup … &`` on
macOS, or a Windows service wrapper).

Debounce & Cooldown
-------------------
File-system events are *debounced*: a sync is only triggered after the
observed directory has been quiet for ``debounce_seconds`` (default 5 s).
After each sync a *cooldown* period (default 10 s) prevents the watcher from
reacting to the changes that were just written by the sync itself, which
avoids accidental push → pull → push loops on a single machine.
"""

from __future__ import annotations

import functools
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from . import sync as sync_module

# ---------------------------------------------------------------------------
# Optional watchdog import – resolved at module level for testability
# ---------------------------------------------------------------------------

try:
    from watchdog.events import FileSystemEventHandler as _FileSystemEventHandler
    from watchdog.observers import Observer as _Observer

    _WATCHDOG_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FileSystemEventHandler = object  # type: ignore[assignment,misc]
    _Observer = None  # type: ignore[assignment]
    _WATCHDOG_AVAILABLE = False

# Re-export under un-prefixed names so tests can patch them easily.
Observer = _Observer
FileSystemEventHandler = _FileSystemEventHandler


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _DebounceTimer:
    """One-shot timer that resets itself on every :meth:`trigger` call.

    When the timer fires (i.e. no new ``trigger()`` calls arrived within
    *seconds*), *callback* is invoked from a daemon thread.

    Args:
        seconds: Quiet period before the callback is invoked.
        callback: Callable to invoke once the timer fires.
    """

    def __init__(self, seconds: float, callback: Callable[[], None]) -> None:
        self._seconds = seconds
        self._callback = callback
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def trigger(self) -> None:
        """Reset (or start) the countdown."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._seconds, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self) -> None:
        """Cancel a pending timer without invoking the callback."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
        self._callback()


class _WatchState:
    """Shared mutable state for the watcher (debounce timers + cooldowns).

    Args:
        debounce_seconds: Quiet period before a sync is triggered.
        cooldown_seconds: Period after a sync during which new events are
            silently ignored to prevent loop-back reactions.
    """

    def __init__(
        self,
        debounce_seconds: float = 5.0,
        cooldown_seconds: float = 10.0,
    ) -> None:
        self._debounce = debounce_seconds
        self._cooldown = cooldown_seconds
        self._lock = threading.Lock()
        self._cooldown_until: dict[str, float] = {}
        self._timers: dict[str, _DebounceTimer] = {}

    def on_change(
        self,
        key: str,
        callback: Callable[[], None],
        on_event: Optional[Callable[[str], None]],
    ) -> None:
        """Called by the file-system event handler when a change is detected.

        Args:
            key: Logical name for this watcher (``"push"`` or ``"pull"``).
            callback: The sync function to call when the debounce timer fires.
            on_event: Optional callable for status messages.
        """
        with self._lock:
            if time.monotonic() < self._cooldown_until.get(key, 0):
                return  # Ignore: we are in the post-sync cooldown period.

            if key not in self._timers:
                self._timers[key] = _DebounceTimer(
                    self._debounce,
                    functools.partial(self._fire, key, callback, on_event),
                )
            self._timers[key].trigger()

    def _fire(
        self,
        key: str,
        callback: Callable[[], None],
        on_event: Optional[Callable[[str], None]],
    ) -> None:
        """Invoke *callback* and set up the post-sync cooldown."""
        def _log(msg: str) -> None:
            if on_event:
                on_event(msg)

        _log(f"Auto-syncing ({key})…")
        try:
            callback()
            _log(f"✓ Auto-sync complete ({key})")
        except Exception as exc:  # pragma: no cover – logged, not re-raised
            _log(f"⚠ Auto-sync failed ({key}): {exc}")
        finally:
            # Cool down both directions to break any potential push/pull loop.
            with self._lock:
                now = time.monotonic()
                self._cooldown_until[key] = now + self._cooldown
                opposite = "pull" if key == "push" else "push"
                self._cooldown_until[opposite] = now + self._cooldown

    def cancel_all(self) -> None:
        """Cancel all pending debounce timers."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def watch(
    profiles_dir: Path,
    sync_dir: Path,
    plugins_dir: Optional[Path] = None,
    push: bool = True,
    pull: bool = True,
    debounce_seconds: float = 5.0,
    on_event: Optional[Callable[[str], None]] = None,
) -> None:
    """Watch directories for changes and automatically push or pull.

    Blocks until interrupted with **Ctrl-C** (``KeyboardInterrupt``).

    When *push* is ``True``, the local *profiles_dir* (and *plugins_dir* when
    provided) are watched.  Any detected change triggers a
    :func:`stream_deck_sync.sync.push` after the debounce period.

    When *pull* is ``True``, the ``profiles`` sub-directory inside *sync_dir*
    is watched.  Any detected change triggers a
    :func:`stream_deck_sync.sync.pull` (without backup) after the debounce
    period.

    Args:
        profiles_dir: Local Stream Deck profiles directory.
        sync_dir: Cloud sync directory.
        plugins_dir: Local Stream Deck plugins directory (optional).
        push: Watch local directories and auto-push on change.
        pull: Watch sync directory and auto-pull on change.
        debounce_seconds: Seconds of file-system quiet before a sync fires.
        on_event: Optional callback that receives human-readable status
            messages (useful for CLI output).

    Raises:
        RuntimeError: When the ``watchdog`` package is not installed.
        ValueError: When neither *push* nor *pull* is ``True``.
    """
    if not push and not pull:
        raise ValueError("At least one of 'push' or 'pull' must be True.")

    if not _WATCHDOG_AVAILABLE:
        raise RuntimeError(
            "The 'watchdog' package is required for file watching.\n"
            "Install it with: pip install \"stream-deck-profile-sync[watch]\""
        )

    def _log(msg: str) -> None:
        if on_event:
            on_event(msg)

    state = _WatchState(
        debounce_seconds=debounce_seconds,
        cooldown_seconds=debounce_seconds * 2,
    )

    class _ChangeHandler(FileSystemEventHandler):
        """Forwards non-directory events to the shared _WatchState."""

        def __init__(self, key: str, callback: Callable[[], None]) -> None:
            super().__init__()
            self._key = key
            self._callback = callback

        def on_any_event(self, event) -> None:  # type: ignore[override]
            if event.is_directory:
                return
            state.on_change(self._key, self._callback, on_event)

    observer = Observer()
    watched: list[str] = []

    if push:
        def _do_push() -> None:
            sync_module.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)

        push_handler = _ChangeHandler("push", _do_push)
        observer.schedule(push_handler, str(profiles_dir), recursive=True)
        watched.append(str(profiles_dir))
        if plugins_dir is not None and plugins_dir.exists():
            observer.schedule(push_handler, str(plugins_dir), recursive=True)
            watched.append(str(plugins_dir))

    if pull:
        sync_profiles_dir = sync_dir / sync_module.PROFILES_SUBDIR
        if sync_profiles_dir.exists():
            def _do_pull() -> None:
                sync_module.pull(
                    profiles_dir, sync_dir, backup=False, plugins_dir=plugins_dir
                )

            pull_handler = _ChangeHandler("pull", _do_pull)
            observer.schedule(pull_handler, str(sync_dir), recursive=True)
            watched.append(str(sync_dir))
        else:
            _log(
                "⚠ Sync directory has no profiles yet – pull watching disabled. "
                "Run 'push' from another machine first."
            )

    if not watched:
        _log("⚠ No directories to watch.")
        return

    observer.start()
    _log("Watching for changes. Press Ctrl-C to stop.")
    for path in watched:
        _log(f"  · {path}")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        state.cancel_all()
        observer.stop()
        observer.join()
