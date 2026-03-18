"""Tests for stream_deck_sync.profiles module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from stream_deck_sync.profiles import get_plugins_dir, get_profiles_dir


class TestGetProfilesDir:
    def test_windows_returns_appdata_path(self):
        appdata = "C:\\Users\\Test\\AppData\\Roaming"
        with mock.patch("platform.system", return_value="Windows"):
            with mock.patch.dict(os.environ, {"APPDATA": appdata}):
                result = get_profiles_dir()
        expected = Path(appdata) / "Elgato" / "StreamDeck" / "ProfilesV2"
        assert result == expected

    def test_darwin_returns_library_path(self):
        home = Path("/Users/test")
        with mock.patch("platform.system", return_value="Darwin"):
            with mock.patch("pathlib.Path.home", return_value=home):
                result = get_profiles_dir()
        expected = (
            home
            / "Library"
            / "Application Support"
            / "com.elgato.StreamDeck"
            / "ProfilesV2"
        )
        assert result == expected

    def test_unsupported_platform_raises_error(self):
        with mock.patch("platform.system", return_value="Linux"):
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                get_profiles_dir()

    def test_windows_missing_appdata_raises_error(self):
        env = {k: v for k, v in os.environ.items() if k != "APPDATA"}
        with mock.patch("platform.system", return_value="Windows"):
            with mock.patch.dict(os.environ, env, clear=True):
                with pytest.raises(RuntimeError, match="APPDATA"):
                    get_profiles_dir()


class TestGetPluginsDir:
    def test_windows_returns_appdata_plugins_path(self):
        appdata = "C:\\Users\\Test\\AppData\\Roaming"
        with mock.patch("platform.system", return_value="Windows"):
            with mock.patch.dict(os.environ, {"APPDATA": appdata}):
                result = get_plugins_dir()
        expected = Path(appdata) / "Elgato" / "StreamDeck" / "Plugins"
        assert result == expected

    def test_darwin_returns_library_plugins_path(self):
        home = Path("/Users/test")
        with mock.patch("platform.system", return_value="Darwin"):
            with mock.patch("pathlib.Path.home", return_value=home):
                result = get_plugins_dir()
        expected = (
            home
            / "Library"
            / "Application Support"
            / "com.elgato.StreamDeck"
            / "Plugins"
        )
        assert result == expected

    def test_unsupported_platform_raises_error(self):
        with mock.patch("platform.system", return_value="Linux"):
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                get_plugins_dir()
