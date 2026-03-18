"""Tests for stream_deck_sync.sync module."""

from __future__ import annotations

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
def sync_dir(tmp_path: Path) -> Path:
    """Empty sync directory."""
    d = tmp_path / "sync"
    d.mkdir()
    return d


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


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------


class TestPull:
    def test_copies_synced_profiles_to_local(
        self, profiles_dir: Path, sync_dir: Path, tmp_path: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        new_local = tmp_path / "new_profiles"
        sync.pull(new_local, sync_dir, backup=False)
        assert new_local.exists()
        assert (new_local / "ABC123.sdProfile").exists()

    def test_creates_backup_by_default(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        _, backup_dir = sync.pull(profiles_dir, sync_dir, backup=True)
        assert backup_dir is not None
        assert backup_dir.exists()

    def test_no_backup_when_disabled(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        _, backup_dir = sync.pull(profiles_dir, sync_dir, backup=False)
        assert backup_dir is None

    def test_raises_when_no_synced_profiles(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            sync.pull(profiles_dir, sync_dir)

    def test_updates_state_with_last_pull(
        self, profiles_dir: Path, sync_dir: Path
    ) -> None:
        sync.push(profiles_dir, sync_dir)
        state, _ = sync.pull(profiles_dir, sync_dir, backup=False)
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
