# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `status` command now shows local profiles under "Local only" when the sync
  directory is empty (e.g. right after `init` before the first `push`), instead
  of returning early with only a warning.
- `status` command now shows local plugins under "Local only" when no synced
  plugins exist yet, consistent with the profiles behaviour.

## [0.1.0] - 2026-03-18

### Added

- `init` command to configure the sync directory (stored in
  `~/.stream-deck-sync/config.json`).
- `push` command to copy local Stream Deck profiles and plugins to the sync
  directory.
- `pull` command to replace local profiles and plugins with the synced copies,
  with automatic timestamped backups.
- `status` command to compare local and synced profiles and plugins, showing
  modified, local-only, sync-only, and in-sync items with human-readable profile
  names read from `manifest.json`.
- Support for macOS and Windows; auto-detection of the Stream Deck profiles and
  plugins directories.
- `--no-plugins` flag on `push`, `pull`, and `status` to skip plugin handling.
- `--no-backup` flag on `pull` to skip creating backups.
- `--sync-dir`, `--profiles-dir`, and `--plugins-dir` override options on all
  commands.

[Unreleased]: https://github.com/dominik-ba/stream-deck-profile-sync/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dominik-ba/stream-deck-profile-sync/releases/tag/v0.1.0
