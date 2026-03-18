"""Tests for stream_deck_sync.schedule module."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from stream_deck_sync import schedule as schedule_module
from stream_deck_sync.schedule import (
    LAUNCH_AGENT_ID,
    WINDOWS_TASK_NAME,
    _build_command_args,
    _build_plist,
    _get_plist_path,
    describe_schedule,
    disable_schedule,
    enable_schedule,
    get_schedule_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_plist(tmp_path, monkeypatch):
    """Redirect the plist path to a temp directory."""
    plist_path = tmp_path / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
    monkeypatch.setattr(schedule_module, "_get_plist_path", lambda: plist_path)
    return plist_path


# ---------------------------------------------------------------------------
# _build_command_args
# ---------------------------------------------------------------------------


class TestBuildCommandArgs:
    def test_push_minimal(self):
        args = _build_command_args("push", None, None, None, False)
        assert args[:3] == [sys.executable, "-m", "stream_deck_sync"]
        assert args[3] == "push"
        assert "--no-backup" not in args

    def test_pull_adds_no_backup(self):
        args = _build_command_args("pull", None, None, None, False)
        assert "pull" in args
        assert "--no-backup" in args

    def test_with_sync_dir(self, tmp_path):
        args = _build_command_args("push", tmp_path, None, None, False)
        assert "--sync-dir" in args
        idx = args.index("--sync-dir")
        assert args[idx + 1] == str(tmp_path)

    def test_with_profiles_dir(self, tmp_path):
        args = _build_command_args("push", None, tmp_path, None, False)
        assert "--profiles-dir" in args

    def test_with_plugins_dir(self, tmp_path):
        args = _build_command_args("push", None, None, tmp_path, False)
        assert "--plugins-dir" in args

    def test_no_plugins_flag(self):
        args = _build_command_args("push", None, None, None, True)
        assert "--no-plugins" in args

    def test_no_plugins_false_not_included(self):
        args = _build_command_args("push", None, None, None, False)
        assert "--no-plugins" not in args


# ---------------------------------------------------------------------------
# _build_plist
# ---------------------------------------------------------------------------


class TestBuildPlist:
    def _parse(self, data: bytes) -> dict:
        return plistlib.loads(data)

    def test_label(self):
        args = [sys.executable, "-m", "stream_deck_sync", "push"]
        parsed = self._parse(_build_plist(args, 30))
        assert parsed["Label"] == LAUNCH_AGENT_ID

    def test_program_arguments(self):
        args = [sys.executable, "-m", "stream_deck_sync", "pull", "--no-backup"]
        parsed = self._parse(_build_plist(args, 15))
        assert parsed["ProgramArguments"] == args

    def test_start_interval_minutes_to_seconds(self):
        args = [sys.executable, "-m", "stream_deck_sync", "push"]
        parsed = self._parse(_build_plist(args, 30))
        assert parsed["StartInterval"] == 1800

    def test_run_at_load_false(self):
        args = [sys.executable, "-m", "stream_deck_sync", "push"]
        parsed = self._parse(_build_plist(args, 10))
        assert parsed["RunAtLoad"] is False

    def test_log_path_under_home(self):
        args = [sys.executable, "-m", "stream_deck_sync", "push"]
        parsed = self._parse(_build_plist(args, 5))
        expected_log = str(
            Path.home() / "Library" / "Logs" / "stream-deck-sync.log"
        )
        assert parsed["StandardOutPath"] == expected_log
        assert parsed["StandardErrorPath"] == expected_log


# ---------------------------------------------------------------------------
# macOS schedule functions
# ---------------------------------------------------------------------------


class TestEnableScheduleMacOS:
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_enable_creates_plist_and_calls_launchctl(self, tmp_plist):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            enable_schedule(30, "push")

        assert tmp_plist.exists()
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("load" in c for c in calls)

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_enable_unloads_existing_plist_first(self, tmp_plist):
        # Pre-create the plist so the "unload" branch is exercised.
        tmp_plist.parent.mkdir(parents=True, exist_ok=True)
        tmp_plist.write_bytes(b"<plist/>")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            enable_schedule(15, "pull")

        args_lists = [c.args[0] for c in mock_run.call_args_list]
        assert any("unload" in a for a in args_lists)


class TestDisableScheduleMacOS:
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_disable_raises_when_no_plist(self, tmp_plist):
        with pytest.raises(RuntimeError, match="No stream-deck-sync schedule"):
            disable_schedule()

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_disable_removes_plist(self, tmp_plist):
        tmp_plist.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, "-m", "stream_deck_sync", "push"]
        tmp_plist.write_bytes(_build_plist(args, 30))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            disable_schedule()

        assert not tmp_plist.exists()


class TestGetStatusMacOS:
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_status_disabled_when_no_plist(self, tmp_plist):
        result = get_schedule_status()
        assert result == {"enabled": False}

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_status_enabled_reads_action_and_interval(self, tmp_plist):
        tmp_plist.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, "-m", "stream_deck_sync", "push"]
        tmp_plist.write_bytes(_build_plist(args, 20))

        result = get_schedule_status()

        assert result["enabled"] is True
        assert result["action"] == "push"
        assert result["interval_minutes"] == 20


# ---------------------------------------------------------------------------
# Cross-platform unit tests (no actual subprocess calls)
# ---------------------------------------------------------------------------


class TestEnableSchedulePlatformGuard:
    def test_invalid_action_raises_value_error(self):
        with pytest.raises(ValueError, match="action must be"):
            enable_schedule(30, "sync")

    @pytest.mark.skipif(
        sys.platform in ("darwin", "win32"), reason="Linux/other only"
    )
    def test_raises_on_unsupported_platform(self):
        with pytest.raises(RuntimeError, match="only supported on macOS and Windows"):
            enable_schedule(30, "push")


class TestDisableSchedulePlatformGuard:
    @pytest.mark.skipif(
        sys.platform in ("darwin", "win32"), reason="Linux/other only"
    )
    def test_raises_on_unsupported_platform(self):
        with pytest.raises(RuntimeError, match="only supported on macOS and Windows"):
            disable_schedule()


class TestGetScheduleStatusPlatformGuard:
    @pytest.mark.skipif(
        sys.platform in ("darwin", "win32"), reason="Linux/other only"
    )
    def test_returns_disabled_on_unsupported_platform(self):
        result = get_schedule_status()
        assert result == {"enabled": False}


# ---------------------------------------------------------------------------
# Mocked macOS tests (run on any platform for better CI coverage)
# ---------------------------------------------------------------------------


class TestEnableScheduleMacOSMocked:
    def test_enable_push_writes_valid_plist(self, tmp_path, monkeypatch):
        plist_path = (
            tmp_path / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
        )
        monkeypatch.setattr(schedule_module, "_get_plist_path", lambda: plist_path)
        monkeypatch.setattr("sys.platform", "darwin")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            from stream_deck_sync.schedule import _enable_schedule_macos

            _enable_schedule_macos(30, "push", None, None, None, False)

        assert plist_path.exists()
        parsed = plistlib.loads(plist_path.read_bytes())
        assert parsed["Label"] == LAUNCH_AGENT_ID
        assert parsed["StartInterval"] == 1800

    def test_enable_pull_includes_no_backup(self, tmp_path, monkeypatch):
        plist_path = (
            tmp_path / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
        )
        monkeypatch.setattr(schedule_module, "_get_plist_path", lambda: plist_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            from stream_deck_sync.schedule import _enable_schedule_macos

            _enable_schedule_macos(15, "pull", None, None, None, False)

        parsed = plistlib.loads(plist_path.read_bytes())
        assert "--no-backup" in parsed["ProgramArguments"]

    def test_enable_unloads_old_plist(self, tmp_path, monkeypatch):
        plist_path = (
            tmp_path / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
        )
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_bytes(b"<plist/>")
        monkeypatch.setattr(schedule_module, "_get_plist_path", lambda: plist_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            from stream_deck_sync.schedule import _enable_schedule_macos

            _enable_schedule_macos(30, "push", None, None, None, False)

        call_args = [c.args[0] for c in mock_run.call_args_list]
        unload_calls = [a for a in call_args if "unload" in a]
        assert unload_calls, "Expected launchctl unload to be called"

    def test_disable_raises_when_no_plist(self, tmp_path, monkeypatch):
        plist_path = (
            tmp_path / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
        )
        monkeypatch.setattr(schedule_module, "_get_plist_path", lambda: plist_path)
        from stream_deck_sync.schedule import _disable_schedule_macos

        with pytest.raises(RuntimeError):
            _disable_schedule_macos()

    def test_disable_removes_plist_and_unloads(self, tmp_path, monkeypatch):
        plist_path = (
            tmp_path / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
        )
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, "-m", "stream_deck_sync", "push"]
        plist_path.write_bytes(_build_plist(args, 30))
        monkeypatch.setattr(schedule_module, "_get_plist_path", lambda: plist_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            from stream_deck_sync.schedule import _disable_schedule_macos

            _disable_schedule_macos()

        assert not plist_path.exists()

    def test_get_status_disabled(self, tmp_path, monkeypatch):
        plist_path = (
            tmp_path / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
        )
        monkeypatch.setattr(schedule_module, "_get_plist_path", lambda: plist_path)
        from stream_deck_sync.schedule import _get_status_macos

        assert _get_status_macos() == {"enabled": False}

    def test_get_status_enabled_returns_action_and_interval(
        self, tmp_path, monkeypatch
    ):
        plist_path = (
            tmp_path / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
        )
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, "-m", "stream_deck_sync", "pull", "--no-backup"]
        plist_path.write_bytes(_build_plist(args, 10))
        monkeypatch.setattr(schedule_module, "_get_plist_path", lambda: plist_path)
        from stream_deck_sync.schedule import _get_status_macos

        result = _get_status_macos()
        assert result["enabled"] is True
        assert result["action"] == "pull"
        assert result["interval_minutes"] == 10


# ---------------------------------------------------------------------------
# Mocked Windows tests (run on any platform for better CI coverage)
# ---------------------------------------------------------------------------


class TestEnableScheduleWindowsMocked:
    def test_creates_scheduled_task(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            from stream_deck_sync.schedule import _enable_schedule_windows

            _enable_schedule_windows(30, "push", None, None, None, False)

        create_calls = [
            c for c in mock_run.call_args_list if "/Create" in str(c)
        ]
        assert create_calls, "Expected schtasks /Create to be called"

    def test_deletes_existing_task_first(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            from stream_deck_sync.schedule import _enable_schedule_windows

            _enable_schedule_windows(15, "pull", None, None, None, False)

        delete_calls = [
            c for c in mock_run.call_args_list if "/Delete" in str(c)
        ]
        assert delete_calls

    def test_disable_raises_when_task_missing(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            from stream_deck_sync.schedule import _disable_schedule_windows

            with pytest.raises(RuntimeError):
                _disable_schedule_windows()

    def test_get_status_disabled_when_task_missing(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            from stream_deck_sync.schedule import _get_status_windows

            result = _get_status_windows()
            assert result == {"enabled": False}

    def test_get_status_enabled_when_task_exists(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="task,running")
            from stream_deck_sync.schedule import _get_status_windows

            result = _get_status_windows()
            assert result["enabled"] is True


# ---------------------------------------------------------------------------
# describe_schedule helper
# ---------------------------------------------------------------------------


class TestDescribeSchedule:
    def test_disabled(self):
        assert describe_schedule({"enabled": False}) == "No schedule configured."

    def test_enabled_push(self):
        msg = describe_schedule(
            {"enabled": True, "action": "push", "interval_minutes": 30}
        )
        assert "push" in msg
        assert "30" in msg

    def test_enabled_pull(self):
        msg = describe_schedule(
            {"enabled": True, "action": "pull", "interval_minutes": 15}
        )
        assert "pull" in msg
        assert "15" in msg
