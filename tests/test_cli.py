"""Tests for stream_deck_sync.cli module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from stream_deck_sync import schedule as schedule_mod
from stream_deck_sync import sync as sync_module
from stream_deck_sync import watcher as watcher_mod
from stream_deck_sync.cli import cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def profiles_dir(tmp_path: Path) -> Path:
    """Minimal fake Stream Deck profiles directory."""
    profiles = tmp_path / "ProfilesV2"
    profiles.mkdir()

    profile1 = profiles / "ABC123.sdProfile"
    profile1.mkdir()
    (profile1 / "manifest.json").write_text('{"Name": "Profile 1"}', encoding="utf-8")
    (profile1 / "page.json").write_text('{"buttons": []}', encoding="utf-8")

    profile2 = profiles / "DEF456.sdProfile"
    profile2.mkdir()
    (profile2 / "manifest.json").write_text('{"Name": "Profile 2"}', encoding="utf-8")

    return profiles


@pytest.fixture()
def plugins_dir(tmp_path: Path) -> Path:
    """Minimal fake Stream Deck plugins directory."""
    plugins = tmp_path / "Plugins"
    plugins.mkdir()

    plugin1 = plugins / "com.example.myplugin.sdPlugin"
    plugin1.mkdir()
    (plugin1 / "manifest.json").write_text('{"Name": "My Plugin"}', encoding="utf-8")

    return plugins


@pytest.fixture()
def sync_dir(tmp_path: Path) -> Path:
    """Empty sync directory."""
    d = tmp_path / "sync"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


class TestStatusCommand:
    def test_shows_local_profiles_when_sync_is_empty(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        """After init (empty sync dir), status should show local profiles."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "status",
                "--sync-dir", str(sync_dir),
                "--profiles-dir", str(profiles_dir),
                "--no-plugins",
            ],
        )
        assert result.exit_code == 0
        assert "No synced profiles found" in result.output
        assert "Local only" in result.output
        # Both local profiles should appear in the output
        assert "Profile 1" in result.output
        assert "Profile 2" in result.output

    def test_returns_early_when_no_local_and_no_sync(
        self, tmp_path: Path, sync_dir: Path
    ) -> None:
        """When neither local nor sync profiles exist, exit after the warnings."""
        runner = CliRunner()
        nonexistent_profiles = tmp_path / "NoProfiles"
        result = runner.invoke(
            cli,
            [
                "status",
                "--sync-dir", str(sync_dir),
                "--profiles-dir", str(nonexistent_profiles),
                "--no-plugins",
            ],
        )
        assert result.exit_code == 0
        assert "Local profiles directory not found" in result.output
        assert "No synced profiles found" in result.output
        # Should NOT show profile listing entries (only the warnings)
        assert "Local only" not in result.output
        assert "in sync" not in result.output

    def test_shows_all_in_sync_after_push(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        """After a push, status should show all profiles in sync."""
        sync_module.push(profiles_dir, sync_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "status",
                "--sync-dir", str(sync_dir),
                "--profiles-dir", str(profiles_dir),
                "--no-plugins",
            ],
        )
        assert result.exit_code == 0
        assert "in sync" in result.output
        assert "No synced profiles found" not in result.output

    def test_shows_local_plugins_when_sync_plugins_empty(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        """When sync dir has profiles but no plugins, show local plugins."""
        # Push only profiles, not plugins
        sync_module.push(profiles_dir, sync_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "status",
                "--sync-dir", str(sync_dir),
                "--profiles-dir", str(profiles_dir),
                "--plugins-dir", str(plugins_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No synced plugins found" in result.output
        assert "Local only" in result.output
        assert "My Plugin" in result.output


# ---------------------------------------------------------------------------
# schedule command group
# ---------------------------------------------------------------------------


class TestScheduleCommands:
    def test_schedule_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["schedule", "--help"])
        assert result.exit_code == 0
        assert "enable" in result.output
        assert "disable" in result.output
        assert "status" in result.output

    def test_schedule_enable_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["schedule", "enable", "--help"])
        assert result.exit_code == 0
        assert "--action" in result.output
        assert "--interval" in result.output

    def test_schedule_enable_invalid_interval(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["schedule", "enable", "--interval", "0", "--action", "push"],
        )
        assert result.exit_code != 0
        assert "interval" in result.output.lower()

    def test_schedule_enable_unsupported_platform(self, monkeypatch) -> None:
        """On non-macOS/Windows, schedule enable shows an error."""
        monkeypatch.setattr(sys, "platform", "linux")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "schedule",
                "enable",
                "--action",
                "push",
                "--interval",
                "30",
            ],
        )
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_schedule_disable_unsupported_platform(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        runner = CliRunner()
        result = runner.invoke(cli, ["schedule", "disable"])
        assert result.exit_code != 0

    def test_schedule_status_no_schedule(self, monkeypatch) -> None:
        """On an unsupported platform get_schedule_status returns disabled."""
        monkeypatch.setattr(sys, "platform", "linux")
        runner = CliRunner()
        result = runner.invoke(cli, ["schedule", "status"])
        assert result.exit_code == 0
        assert "No schedule configured" in result.output

    def test_schedule_enable_mocked_macos(self, monkeypatch, tmp_path) -> None:
        """schedule enable succeeds with mocked launchctl."""
        plist_path = (
            tmp_path
            / "Library"
            / "LaunchAgents"
            / f"{schedule_mod.LAUNCH_AGENT_ID}.plist"
        )
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(schedule_mod, "_get_plist_path", lambda: plist_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["schedule", "enable", "--action", "push", "--interval", "30"],
            )
        assert result.exit_code == 0
        assert "Scheduled push" in result.output


# ---------------------------------------------------------------------------
# watch command
# ---------------------------------------------------------------------------


class TestWatchCommand:
    def test_watch_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "--help"])
        assert result.exit_code == 0
        assert "--push" in result.output or "--no-push" in result.output
        assert "--pull" in result.output or "--no-pull" in result.output
        assert "--debounce" in result.output

    def test_watch_requires_push_or_pull(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "watch",
                "--no-push",
                "--no-pull",
                "--sync-dir",
                str(sync_dir),
                "--profiles-dir",
                str(profiles_dir),
                "--no-plugins",
            ],
        )
        assert result.exit_code != 0

    def test_watch_missing_watchdog_shows_error(
        self, profiles_dir: Path, sync_dir: Path, monkeypatch
    ) -> None:
        """When watchdog is unavailable, watch shows a friendly error."""
        monkeypatch.setattr(watcher_mod, "_WATCHDOG_AVAILABLE", False)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "watch",
                "--sync-dir",
                str(sync_dir),
                "--profiles-dir",
                str(profiles_dir),
                "--no-plugins",
            ],
        )
        assert result.exit_code != 0
        assert "watchdog" in result.output.lower()

    def test_watch_runs_and_stops(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        """watch command starts observer and stops on interrupt."""
        # Create sync profiles so pull watcher can start
        sync_module.push(profiles_dir, sync_dir)

        mock_observer = MagicMock()
        sleep_count = [0]

        def fast_sleep(_):
            sleep_count[0] += 1
            if sleep_count[0] >= 1:
                raise KeyboardInterrupt

        with patch.object(watcher_mod, "Observer", return_value=mock_observer):
            with patch("stream_deck_sync.watcher.time.sleep", fast_sleep):
                runner = CliRunner()
                result = runner.invoke(
                    cli,
                    [
                        "watch",
                        "--sync-dir",
                        str(sync_dir),
                        "--profiles-dir",
                        str(profiles_dir),
                        "--no-plugins",
                    ],
                )

        assert result.exit_code == 0
        assert "Watching" in result.output
