"""Tests for stream_deck_sync.cli module."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

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
        from stream_deck_sync import sync as sync_module

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
        from stream_deck_sync import sync as sync_module

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
