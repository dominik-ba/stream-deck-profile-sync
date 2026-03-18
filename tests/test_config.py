"""Tests for stream_deck_sync.config module."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from stream_deck_sync import config


class TestLoadConfig:
    def test_returns_empty_dict_when_no_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        with mock.patch.object(config, "CONFIG_FILE", config_file):
            result = config.load_config()
        assert result == {}

    def test_returns_saved_values(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"sync_dir": "/some/path"}', encoding="utf-8")
        with mock.patch.object(config, "CONFIG_FILE", config_file):
            result = config.load_config()
        assert result == {"sync_dir": "/some/path"}


class TestSaveConfig:
    def test_creates_file_with_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        with (
            mock.patch.object(config, "CONFIG_FILE", config_file),
            mock.patch.object(config, "CONFIG_DIR", tmp_path),
        ):
            config.save_config({"sync_dir": "/test"})
        assert config_file.exists()

    def test_creates_parent_directories(self, tmp_path):
        config_file = tmp_path / "nested" / "dir" / "config.json"
        config_dir = tmp_path / "nested" / "dir"
        with (
            mock.patch.object(config, "CONFIG_FILE", config_file),
            mock.patch.object(config, "CONFIG_DIR", config_dir),
        ):
            config.save_config({"key": "value"})
        assert config_file.exists()

    def test_roundtrip(self, tmp_path):
        config_file = tmp_path / "config.json"
        test_config = {"sync_dir": "/roundtrip", "extra": 42}
        with (
            mock.patch.object(config, "CONFIG_FILE", config_file),
            mock.patch.object(config, "CONFIG_DIR", tmp_path),
        ):
            config.save_config(test_config)
            result = config.load_config()
        assert result == test_config


class TestGetSyncDir:
    def test_returns_none_when_not_configured(self, tmp_path):
        config_file = tmp_path / "config.json"
        with mock.patch.object(config, "CONFIG_FILE", config_file):
            result = config.get_sync_dir()
        assert result is None

    def test_returns_configured_path(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"sync_dir": "/my/sync"}', encoding="utf-8")
        with mock.patch.object(config, "CONFIG_FILE", config_file):
            result = config.get_sync_dir()
        assert result == Path("/my/sync")


class TestSetSyncDir:
    def test_persists_sync_dir(self, tmp_path):
        config_file = tmp_path / "config.json"
        with (
            mock.patch.object(config, "CONFIG_FILE", config_file),
            mock.patch.object(config, "CONFIG_DIR", tmp_path),
        ):
            config.set_sync_dir(Path("/my/path"))
            result = config.get_sync_dir()
        assert result == Path("/my/path")

    def test_preserves_existing_keys(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"other_key": "value"}', encoding="utf-8")
        with (
            mock.patch.object(config, "CONFIG_FILE", config_file),
            mock.patch.object(config, "CONFIG_DIR", tmp_path),
        ):
            config.set_sync_dir(Path("/new/path"))
            result = config.load_config()
        assert result["other_key"] == "value"
        assert result["sync_dir"] == "/new/path"
