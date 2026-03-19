"""Tests for stream_deck_sync.sync module."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stream_deck_sync import sync


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
    (plugin1 / "plugin.exe").write_bytes(b"\x00\x01\x02")

    plugin2 = plugins / "com.example.other.sdPlugin"
    plugin2.mkdir()
    (plugin2 / "manifest.json").write_text('{"Name": "Other Plugin"}', encoding="utf-8")

    return plugins


@pytest.fixture()
def sync_dir(tmp_path: Path) -> Path:
    """Empty sync directory."""
    d = tmp_path / "sync"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# read_manifest_name
# ---------------------------------------------------------------------------


class TestReadManifestName:
    def test_returns_name_from_manifest(self, tmp_path: Path) -> None:
        folder = tmp_path / "ABC123.sdProfile"
        folder.mkdir()
        (folder / "manifest.json").write_text('{"Name": "My Profile"}', encoding="utf-8")
        assert sync.read_manifest_name(tmp_path, "ABC123.sdProfile") == "My Profile"

    def test_falls_back_to_folder_name_when_no_manifest(self, tmp_path: Path) -> None:
        assert sync.read_manifest_name(tmp_path, "ABC123.sdProfile") == "ABC123.sdProfile"

    def test_falls_back_when_manifest_has_no_name(self, tmp_path: Path) -> None:
        folder = tmp_path / "ABC123.sdProfile"
        folder.mkdir()
        (folder / "manifest.json").write_text('{"Other": "value"}', encoding="utf-8")
        assert sync.read_manifest_name(tmp_path, "ABC123.sdProfile") == "ABC123.sdProfile"

    def test_falls_back_when_manifest_is_invalid_json(self, tmp_path: Path) -> None:
        folder = tmp_path / "ABC123.sdProfile"
        folder.mkdir()
        (folder / "manifest.json").write_text("not json", encoding="utf-8")
        assert sync.read_manifest_name(tmp_path, "ABC123.sdProfile") == "ABC123.sdProfile"


# ---------------------------------------------------------------------------
# _group_by_top_dir
# ---------------------------------------------------------------------------


class TestGroupByTopDir:
    def test_groups_by_first_component(self) -> None:
        paths = [
            "ABC123.sdProfile/manifest.json",
            "ABC123.sdProfile/page.json",
            "DEF456.sdProfile/manifest.json",
        ]
        result = sync._group_by_top_dir(paths)
        assert set(result.keys()) == {"ABC123.sdProfile", "DEF456.sdProfile"}
        assert "manifest.json" in result["ABC123.sdProfile"]
        assert "page.json" in result["ABC123.sdProfile"]

    def test_single_component_path(self) -> None:
        result = sync._group_by_top_dir(["lone_file.txt"])
        assert "lone_file.txt" in result


# ---------------------------------------------------------------------------
# compute_dir_state
# ---------------------------------------------------------------------------


class TestComputeDirState:
    def test_empty_directory(self, tmp_path: Path) -> None:
        assert sync.compute_dir_state(tmp_path) == {}

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        assert sync.compute_dir_state(tmp_path / "nonexistent") == {}

    def test_computes_md5_hashes(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
        result = sync.compute_dir_state(tmp_path)
        assert "file.txt" in result
        assert len(result["file.txt"]) == 32  # MD5 hex length

    def test_consistent_across_calls(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
        assert sync.compute_dir_state(tmp_path) == sync.compute_dir_state(tmp_path)

    def test_different_content_produces_different_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello", encoding="utf-8")
        hash1 = sync.compute_dir_state(tmp_path)["file.txt"]
        f.write_text("world", encoding="utf-8")
        hash2 = sync.compute_dir_state(tmp_path)["file.txt"]
        assert hash1 != hash2

    def test_nested_files_use_posix_paths(self, tmp_path: Path) -> None:
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("hello", encoding="utf-8")
        result = sync.compute_dir_state(tmp_path)
        assert "subdir/file.txt" in result

    def test_excludes_log_files_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")
        (tmp_path / "pluginlog.log").write_text("log data", encoding="utf-8")
        result = sync.compute_dir_state(tmp_path)
        assert "data.json" in result
        assert "pluginlog.log" not in result

    def test_excludes_files_matching_custom_pattern(self, tmp_path: Path) -> None:
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")
        (tmp_path / "cache.tmp").write_text("temp", encoding="utf-8")
        result = sync.compute_dir_state(tmp_path, exclude_patterns=["*.tmp"])
        assert "data.json" in result
        assert "cache.tmp" not in result

    def test_empty_exclude_patterns_includes_all_files(self, tmp_path: Path) -> None:
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")
        (tmp_path / "pluginlog.log").write_text("log data", encoding="utf-8")
        result = sync.compute_dir_state(tmp_path, exclude_patterns=[])
        assert "data.json" in result
        assert "pluginlog.log" in result

    def test_excludes_log_files_in_subdirectories(self, tmp_path: Path) -> None:
        plugin = tmp_path / "com.example.plugin.sdPlugin"
        plugin.mkdir()
        (plugin / "manifest.json").write_text('{"Name": "Plugin"}', encoding="utf-8")
        (plugin / "pluginlog.log").write_text("log data", encoding="utf-8")
        result = sync.compute_dir_state(tmp_path)
        assert "com.example.plugin.sdPlugin/manifest.json" in result
        assert "com.example.plugin.sdPlugin/pluginlog.log" not in result


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------


class TestPush:
    def test_copies_profiles_to_sync_dir(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        assert (sync_dir / "profiles").exists()
        assert (sync_dir / "profiles" / "ABC123.sdProfile").exists()

    def test_creates_state_file(self, profiles_dir: Path, sync_dir: Path) -> None:
        sync.push(profiles_dir, sync_dir)
        assert (sync_dir / sync.STATE_FILE).exists()

    def test_state_contains_last_push(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        state = sync.push(profiles_dir, sync_dir)
        assert "last_push" in state

    def test_state_contains_file_hashes(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        state = sync.push(profiles_dir, sync_dir)
        assert "profiles_state" in state
        assert len(state["profiles_state"]) > 0

    def test_raises_when_profiles_dir_missing(
        self, tmp_path: Path, sync_dir: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            sync.push(tmp_path / "nonexistent", sync_dir)

    def test_overwrites_stale_sync_data(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        # Inject a stale file that no longer exists locally.
        stale = sync_dir / "profiles" / "STALE.sdProfile" / "manifest.json"
        stale.parent.mkdir(parents=True)
        stale.write_text('{"Name": "Stale"}', encoding="utf-8")
        sync.push(profiles_dir, sync_dir)
        assert not stale.exists()

    def test_pushes_plugins_when_provided(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        state = sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        assert (sync_dir / "plugins").exists()
        assert (sync_dir / "plugins" / "com.example.myplugin.sdPlugin").exists()
        assert "plugins_state" in state
        assert len(state["plugins_state"]) > 0

    def test_no_plugins_in_state_when_not_provided(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        state = sync.push(profiles_dir, sync_dir)
        assert "plugins_state" not in state

    def test_plugins_dir_not_exist_is_silently_skipped(
        self, profiles_dir: Path, sync_dir: Path, tmp_path: Path
    ) -> None:
        state = sync.push(profiles_dir, sync_dir, plugins_dir=tmp_path / "nope")
        assert "plugins_state" not in state

    def test_excluded_files_not_copied_to_sync_dir(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        (profiles_dir / "ABC123.sdProfile" / "pluginlog.log").write_text(
            "log data", encoding="utf-8"
        )
        sync.push(profiles_dir, sync_dir)
        assert not (
            sync_dir / "profiles" / "ABC123.sdProfile" / "pluginlog.log"
        ).exists()

    def test_excluded_files_not_in_profiles_state(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        (profiles_dir / "ABC123.sdProfile" / "pluginlog.log").write_text(
            "log data", encoding="utf-8"
        )
        state = sync.push(profiles_dir, sync_dir)
        assert not any(
            k.endswith("pluginlog.log") for k in state["profiles_state"]
        )

    def test_excluded_plugin_files_not_copied_to_sync_dir(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        (plugins_dir / "com.example.myplugin.sdPlugin" / "pluginlog.log").write_text(
            "log data", encoding="utf-8"
        )
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        assert not (
            sync_dir
            / "plugins"
            / "com.example.myplugin.sdPlugin"
            / "pluginlog.log"
        ).exists()

    def test_excluded_plugin_files_not_in_plugins_state(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        (plugins_dir / "com.example.myplugin.sdPlugin" / "pluginlog.log").write_text(
            "log data", encoding="utf-8"
        )
        state = sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        assert not any(
            k.endswith("pluginlog.log") for k in state["plugins_state"]
        )

    def test_custom_exclude_patterns_applied_on_push(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        (profiles_dir / "ABC123.sdProfile" / "cache.tmp").write_text(
            "temp", encoding="utf-8"
        )
        sync.push(profiles_dir, sync_dir, exclude_patterns=["*.tmp"])
        assert not (
            sync_dir / "profiles" / "ABC123.sdProfile" / "cache.tmp"
        ).exists()

    def test_empty_exclude_patterns_copies_log_files(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        (profiles_dir / "ABC123.sdProfile" / "pluginlog.log").write_text(
            "log data", encoding="utf-8"
        )
        sync.push(profiles_dir, sync_dir, exclude_patterns=[])
        assert (
            sync_dir / "profiles" / "ABC123.sdProfile" / "pluginlog.log"
        ).exists()


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------


class TestPull:
    def test_copies_synced_profiles_to_local(
        self, profiles_dir: Path, sync_dir: Path, tmp_path: Path
    ) -> None:
        # Push from profiles_dir, then pull into a separate destination directory.
        sync.push(profiles_dir, sync_dir)
        dest_dir = tmp_path / "new_profiles"
        sync.pull(dest_dir, sync_dir, backup=False)
        assert dest_dir.exists()
        assert (dest_dir / "ABC123.sdProfile").exists()

    def test_creates_backup_by_default(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        _, profiles_backup, _ = sync.pull(profiles_dir, sync_dir, backup=True)
        assert profiles_backup is not None
        assert profiles_backup.exists()

    def test_no_backup_when_disabled(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        _, profiles_backup, plugins_backup = sync.pull(
            profiles_dir, sync_dir, backup=False
        )
        assert profiles_backup is None
        assert plugins_backup is None

    def test_raises_when_no_synced_profiles(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            sync.pull(profiles_dir, sync_dir)

    def test_updates_state_with_last_pull(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        state, _, _ = sync.pull(profiles_dir, sync_dir, backup=False)
        assert "last_pull" in state

    def test_replaces_local_with_synced_profiles(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        # Add a local file that does not exist in sync.
        extra = profiles_dir / "EXTRA.sdProfile" / "manifest.json"
        extra.parent.mkdir()
        extra.write_text('{"Name": "Extra"}', encoding="utf-8")
        sync.pull(profiles_dir, sync_dir, backup=False)
        assert not extra.exists()
        assert (profiles_dir / "ABC123.sdProfile").exists()

    def test_pulls_plugins_when_provided(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path, tmp_path: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        new_plugins = tmp_path / "NewPlugins"
        sync.pull(profiles_dir, sync_dir, backup=False, plugins_dir=new_plugins)
        assert new_plugins.exists()
        assert (new_plugins / "com.example.myplugin.sdPlugin").exists()

    def test_creates_plugins_backup(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        _, _, plugins_backup = sync.pull(
            profiles_dir, sync_dir, backup=True, plugins_dir=plugins_dir
        )
        assert plugins_backup is not None
        assert plugins_backup.exists()

    def test_no_plugins_backup_when_disabled(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        _, _, plugins_backup = sync.pull(
            profiles_dir, sync_dir, backup=False, plugins_dir=plugins_dir
        )
        assert plugins_backup is None


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_reports_no_sync_when_empty(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        result = sync.status(profiles_dir, sync_dir)
        assert result["has_local"] is True
        assert result["has_sync"] is False

    def test_all_in_sync_after_push(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        result = sync.status(profiles_dir, sync_dir)
        assert result["modified"] == []
        assert result["local_only"] == []
        assert result["sync_only"] == []
        assert len(result["in_sync"]) > 0

    def test_detects_local_only_files(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        new_profile = profiles_dir / "NEW.sdProfile" / "manifest.json"
        new_profile.parent.mkdir()
        new_profile.write_text('{"Name": "New"}', encoding="utf-8")
        result = sync.status(profiles_dir, sync_dir)
        assert "NEW.sdProfile/manifest.json" in result["local_only"]

    def test_detects_sync_only_files(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        shutil.rmtree(profiles_dir / "ABC123.sdProfile")
        result = sync.status(profiles_dir, sync_dir)
        assert len(result["sync_only"]) > 0

    def test_detects_modified_files(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        (profiles_dir / "ABC123.sdProfile" / "manifest.json").write_text(
            '{"Name": "Modified"}', encoding="utf-8"
        )
        result = sync.status(profiles_dir, sync_dir)
        assert "ABC123.sdProfile/manifest.json" in result["modified"]

    def test_includes_last_push_and_pull_timestamps(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        sync.pull(profiles_dir, sync_dir, backup=False)
        result = sync.status(profiles_dir, sync_dir)
        assert result["last_push"] is not None
        assert result["last_pull"] is not None

    def test_plugins_keys_empty_when_not_requested(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        result = sync.status(profiles_dir, sync_dir)
        assert result["plugins_local_only"] == []
        assert result["plugins_sync_only"] == []
        assert result["plugins_modified"] == []
        assert result["plugins_in_sync"] == []
        assert result["has_local_plugins"] is False
        assert result["has_sync_plugins"] is False

    def test_plugins_all_in_sync_after_push(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        result = sync.status(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        assert result["plugins_modified"] == []
        assert result["plugins_local_only"] == []
        assert result["plugins_sync_only"] == []
        assert len(result["plugins_in_sync"]) > 0
        assert result["has_sync_plugins"] is True

    def test_plugins_detects_local_only(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        new_plugin = plugins_dir / "com.example.new.sdPlugin" / "manifest.json"
        new_plugin.parent.mkdir()
        new_plugin.write_text('{"Name": "New Plugin"}', encoding="utf-8")
        result = sync.status(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        assert "com.example.new.sdPlugin/manifest.json" in result["plugins_local_only"]

    def test_plugins_detects_modified(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        (plugins_dir / "com.example.myplugin.sdPlugin" / "manifest.json").write_text(
            '{"Name": "Updated Plugin"}', encoding="utf-8"
        )
        result = sync.status(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        assert (
            "com.example.myplugin.sdPlugin/manifest.json"
            in result["plugins_modified"]
        )

    def test_log_files_not_reported_as_modified(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        # Simulate a plugin writing a log file locally after the push.
        (plugins_dir / "com.example.myplugin.sdPlugin" / "pluginlog.log").write_text(
            "new log entry", encoding="utf-8"
        )
        result = sync.status(profiles_dir, sync_dir, plugins_dir=plugins_dir)
        assert result["plugins_modified"] == []
        assert not any(
            k.endswith("pluginlog.log") for k in result["plugins_local_only"]
        )

    def test_log_files_excluded_by_default_in_profiles_too(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        (profiles_dir / "ABC123.sdProfile" / "debug.log").write_text(
            "debug info", encoding="utf-8"
        )
        result = sync.status(profiles_dir, sync_dir)
        assert result["modified"] == []
        assert not any(k.endswith("debug.log") for k in result["local_only"])

    def test_empty_exclude_patterns_reports_log_file_changes(
        self, profiles_dir: Path, plugins_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir, plugins_dir=plugins_dir, exclude_patterns=[])
        (plugins_dir / "com.example.myplugin.sdPlugin" / "pluginlog.log").write_text(
            "new log entry", encoding="utf-8"
        )
        result = sync.status(
            profiles_dir, sync_dir, plugins_dir=plugins_dir, exclude_patterns=[]
        )
        assert any(
            k.endswith("pluginlog.log") for k in result["plugins_local_only"]
        )

