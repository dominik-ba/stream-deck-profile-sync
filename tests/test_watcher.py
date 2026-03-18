"""Tests for stream_deck_sync.watcher module."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from stream_deck_sync import watcher as watcher_module
from stream_deck_sync.watcher import _DebounceTimer, _WatchState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_profile_tree(tmp_path):
    """Factory: create a minimal local + sync directory structure."""

    def _make(name: str = "test"):
        local = tmp_path / "local" / name
        sync = tmp_path / "sync" / name
        local.mkdir(parents=True)
        sync.mkdir(parents=True)
        return local, sync

    return _make


# ---------------------------------------------------------------------------
# _DebounceTimer
# ---------------------------------------------------------------------------


class TestDebounceTimer:
    def test_callback_fires_after_quiet_period(self):
        fired = threading.Event()
        timer = _DebounceTimer(0.05, fired.set)
        timer.trigger()
        assert fired.wait(timeout=1.0), "Timer did not fire within 1 second"

    def test_reset_delays_callback(self):
        calls: list[float] = []
        start = time.monotonic()

        def record():
            calls.append(time.monotonic() - start)

        timer = _DebounceTimer(0.1, record)
        timer.trigger()
        time.sleep(0.05)
        timer.trigger()  # Reset the timer
        time.sleep(0.15)

        assert len(calls) == 1
        # Callback should have fired ~0.15 s after start (0.05 + 0.10).
        assert calls[0] > 0.12

    def test_cancel_prevents_callback(self):
        fired = threading.Event()
        timer = _DebounceTimer(0.05, fired.set)
        timer.trigger()
        timer.cancel()
        fired.wait(timeout=0.15)
        assert not fired.is_set()

    def test_trigger_after_fire_works_again(self):
        count = [0]

        def inc():
            count[0] += 1

        timer = _DebounceTimer(0.05, inc)
        timer.trigger()
        time.sleep(0.1)
        timer.trigger()
        time.sleep(0.1)
        assert count[0] == 2


# ---------------------------------------------------------------------------
# _WatchState
# ---------------------------------------------------------------------------


class TestWatchState:
    def test_on_change_triggers_callback(self):
        fired = threading.Event()
        state = _WatchState(debounce_seconds=0.05, cooldown_seconds=0.0)
        state.on_change("push", fired.set, None)
        assert fired.wait(timeout=1.0)

    def test_on_change_debounces_multiple_events(self):
        calls: list[int] = []
        state = _WatchState(debounce_seconds=0.1, cooldown_seconds=0.0)

        for _ in range(5):
            state.on_change("push", lambda: calls.append(1), None)
            time.sleep(0.02)

        time.sleep(0.2)
        assert len(calls) == 1

    def test_cooldown_blocks_events_after_sync(self):
        calls: list[int] = []
        state = _WatchState(debounce_seconds=0.05, cooldown_seconds=5.0)
        state.on_change("push", lambda: calls.append(1), None)
        time.sleep(0.1)  # Let the timer fire
        # Now fire a second change; should be blocked by cooldown.
        state.on_change("push", lambda: calls.append(2), None)
        time.sleep(0.1)
        assert len(calls) == 1

    def test_cooldown_blocks_opposite_direction(self):
        """Push cooldown should also silence pull events."""
        push_calls: list[int] = []
        pull_calls: list[int] = []
        state = _WatchState(debounce_seconds=0.05, cooldown_seconds=5.0)
        state.on_change("push", lambda: push_calls.append(1), None)
        time.sleep(0.1)
        # Pull event should be blocked by the push cooldown.
        state.on_change("pull", lambda: pull_calls.append(1), None)
        time.sleep(0.1)
        assert push_calls == [1]
        assert pull_calls == []

    def test_on_event_callback_called_with_message(self):
        messages: list[str] = []
        state = _WatchState(debounce_seconds=0.05, cooldown_seconds=0.0)
        state.on_change("push", lambda: None, messages.append)
        time.sleep(0.2)
        assert any("push" in m for m in messages)

    def test_cancel_all_stops_pending_timers(self):
        fired = threading.Event()
        state = _WatchState(debounce_seconds=0.5, cooldown_seconds=0.0)
        state.on_change("push", fired.set, None)
        state.cancel_all()
        fired.wait(timeout=0.7)
        assert not fired.is_set()


# ---------------------------------------------------------------------------
# watch() – happy path with mocked watchdog
# ---------------------------------------------------------------------------


def _make_fake_watchdog():
    """Return mock Observer + FileSystemEventHandler classes."""
    FakeObserver = MagicMock()
    instance = FakeObserver.return_value
    instance.is_alive.return_value = True

    FakeHandler = MagicMock

    return FakeObserver, FakeHandler


class TestWatchFunction:
    def test_raises_without_watchdog(self, tmp_path):
        """watch() raises RuntimeError when watchdog is not installed."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        sync_dir = tmp_path / "sync"

        with patch.object(watcher_module, "_WATCHDOG_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="watchdog"):
                watcher_module.watch(
                    profiles_dir=profiles_dir,
                    sync_dir=sync_dir,
                    push=True,
                    pull=False,
                )

    def test_raises_when_neither_push_nor_pull(self, tmp_path):
        """watch() raises ValueError when both push and pull are False."""
        with pytest.raises(ValueError, match="At least one"):
            watcher_module.watch(
                profiles_dir=tmp_path,
                sync_dir=tmp_path,
                push=False,
                pull=False,
            )

    def test_watch_starts_and_stops_observer(self, tmp_path):
        """watch() starts the Observer and stops it cleanly on KeyboardInterrupt."""
        from stream_deck_sync import sync as sync_module

        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        sync_dir = tmp_path / "sync"
        (sync_dir / sync_module.PROFILES_SUBDIR).mkdir(parents=True)

        mock_observer = MagicMock()

        with patch("stream_deck_sync.watcher.Observer", return_value=mock_observer):
            # Make the sleep loop raise immediately after one iteration.
            sleep_call_count = [0]

            def patched_sleep(secs):
                sleep_call_count[0] += 1
                if sleep_call_count[0] >= 1:
                    raise KeyboardInterrupt

            with patch("stream_deck_sync.watcher.time.sleep", patched_sleep):
                messages: list[str] = []
                watcher_module.watch(
                    profiles_dir=profiles_dir,
                    sync_dir=sync_dir,
                    push=True,
                    pull=True,
                    debounce_seconds=5.0,
                    on_event=messages.append,
                )

        mock_observer.start.assert_called_once()
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()

    def test_watch_push_only_does_not_schedule_pull(self, tmp_path):
        """With push=True, pull=False, only local directories are scheduled."""
        from stream_deck_sync import sync as sync_module

        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        sync_dir = tmp_path / "sync"
        (sync_dir / sync_module.PROFILES_SUBDIR).mkdir(parents=True)

        mock_observer = MagicMock()
        scheduled_paths: list[str] = []

        def capture_schedule(handler, path, recursive):
            scheduled_paths.append(path)

        mock_observer.schedule = capture_schedule

        with patch("stream_deck_sync.watcher.Observer", return_value=mock_observer):
            with patch("stream_deck_sync.watcher.time.sleep", side_effect=KeyboardInterrupt):
                watcher_module.watch(
                    profiles_dir=profiles_dir,
                    sync_dir=sync_dir,
                    push=True,
                    pull=False,
                    debounce_seconds=5.0,
                )

        assert str(profiles_dir) in scheduled_paths
        assert str(sync_dir) not in scheduled_paths

    def test_watch_pull_only_schedules_sync_dir(self, tmp_path):
        """With pull=True, push=False, only the sync directory is scheduled."""
        from stream_deck_sync import sync as sync_module

        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        sync_dir = tmp_path / "sync"
        (sync_dir / sync_module.PROFILES_SUBDIR).mkdir(parents=True)

        mock_observer = MagicMock()
        scheduled_paths: list[str] = []

        def capture_schedule(handler, path, recursive):
            scheduled_paths.append(path)

        mock_observer.schedule = capture_schedule

        with patch("stream_deck_sync.watcher.Observer", return_value=mock_observer):
            with patch("stream_deck_sync.watcher.time.sleep", side_effect=KeyboardInterrupt):
                watcher_module.watch(
                    profiles_dir=profiles_dir,
                    sync_dir=sync_dir,
                    push=False,
                    pull=True,
                    debounce_seconds=5.0,
                )

        assert str(profiles_dir) not in scheduled_paths
        assert str(sync_dir) in scheduled_paths

    def test_watch_warns_when_sync_profiles_missing_for_pull(self, tmp_path):
        """When sync/profiles does not exist and pull=True, a warning is emitted."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()  # Exists but no profiles subdir

        mock_observer = MagicMock()
        messages: list[str] = []

        with patch("stream_deck_sync.watcher.Observer", return_value=mock_observer):
            with patch("stream_deck_sync.watcher.time.sleep", side_effect=KeyboardInterrupt):
                watcher_module.watch(
                    profiles_dir=profiles_dir,
                    sync_dir=sync_dir,
                    push=False,
                    pull=True,
                    debounce_seconds=5.0,
                    on_event=messages.append,
                )

        assert any("pull watching disabled" in m for m in messages)

    def test_watch_with_plugins_dir_schedules_plugins(self, tmp_path):
        """When plugins_dir is provided and exists, it is also scheduled."""
        from stream_deck_sync import sync as sync_module

        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        sync_dir = tmp_path / "sync"
        (sync_dir / sync_module.PROFILES_SUBDIR).mkdir(parents=True)

        mock_observer = MagicMock()
        scheduled_paths: list[str] = []

        def capture_schedule(handler, path, recursive):
            scheduled_paths.append(path)

        mock_observer.schedule = capture_schedule

        with patch("stream_deck_sync.watcher.Observer", return_value=mock_observer):
            with patch("stream_deck_sync.watcher.time.sleep", side_effect=KeyboardInterrupt):
                watcher_module.watch(
                    profiles_dir=profiles_dir,
                    sync_dir=sync_dir,
                    plugins_dir=plugins_dir,
                    push=True,
                    pull=False,
                    debounce_seconds=5.0,
                )

        assert str(plugins_dir) in scheduled_paths

    def test_watch_no_dirs_returns_early(self, tmp_path):
        """When no directories can be watched, watch() returns without starting observer."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()  # No profiles subdir

        mock_observer = MagicMock()
        messages: list[str] = []

        with patch("stream_deck_sync.watcher.Observer", return_value=mock_observer):
            # push=False and sync profiles dir missing → nothing to watch
            watcher_module.watch(
                profiles_dir=profiles_dir,
                sync_dir=sync_dir,
                push=False,
                pull=True,
                debounce_seconds=5.0,
                on_event=messages.append,
            )

        mock_observer.start.assert_not_called()
