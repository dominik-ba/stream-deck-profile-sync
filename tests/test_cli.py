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


# ---------------------------------------------------------------------------
# status --diff
# ---------------------------------------------------------------------------


class TestStatusDiff:
    def test_diff_shows_changed_lines_for_modified_file(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        """--diff should print unified diff lines for each modified file."""
        from stream_deck_sync import sync as sync_module

        sync_module.push(profiles_dir, sync_dir)

        # Modify a tracked file locally after the push
        (profiles_dir / "ABC123.sdProfile" / "page.json").write_text(
            '{"buttons": ["new"]}', encoding="utf-8"
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "status",
                "--diff",
                "--sync-dir", str(sync_dir),
                "--profiles-dir", str(profiles_dir),
                "--no-plugins",
            ],
        )
        assert result.exit_code == 0
        assert "Modified" in result.output
        # Unified diff header lines must be present
        assert "--- synced" in result.output
        assert "+++ local" in result.output
        # The changed content should appear in the diff
        assert '{"buttons": ["new"]}' in result.output

    def test_no_diff_lines_without_flag(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        """Without --diff the diff lines must not appear in the output."""
        from stream_deck_sync import sync as sync_module

        sync_module.push(profiles_dir, sync_dir)
        (profiles_dir / "ABC123.sdProfile" / "page.json").write_text(
            '{"buttons": ["new"]}', encoding="utf-8"
        )

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
        assert "Modified" in result.output
        assert "--- synced" not in result.output
        assert "+++ local" not in result.output

    def test_diff_handles_binary_file(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        """--diff must not crash on binary files and should note them."""
        from stream_deck_sync import sync as sync_module

        # Add a binary file (contains null byte → detected as binary)
        (profiles_dir / "ABC123.sdProfile" / "icon.bin").write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        )
        sync_module.push(profiles_dir, sync_dir)

        # Modify the binary file locally
        (profiles_dir / "ABC123.sdProfile" / "icon.bin").write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff"
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "status",
                "--diff",
                "--sync-dir", str(sync_dir),
                "--profiles-dir", str(profiles_dir),
                "--no-plugins",
            ],
        )
        assert result.exit_code == 0
        assert "binary file" in result.output.lower()
        # No crash and no attempt at a textual diff
        assert "--- synced" not in result.output

    def test_diff_not_shown_for_local_only_entries(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        """--diff must only show diffs for modified files, not local-only ones."""
        from stream_deck_sync import sync as sync_module

        sync_module.push(profiles_dir, sync_dir)

        # Add a brand-new profile that has no synced counterpart
        new_profile = profiles_dir / "NEW999.sdProfile"
        new_profile.mkdir()
        (new_profile / "manifest.json").write_text(
            '{"Name": "Brand New"}', encoding="utf-8"
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "status",
                "--diff",
                "--sync-dir", str(sync_dir),
                "--profiles-dir", str(profiles_dir),
                "--no-plugins",
            ],
        )
        assert result.exit_code == 0
        assert "Local only" in result.output
        assert "Brand New" in result.output
        # No diff header for local-only entries
        assert "--- synced" not in result.output
