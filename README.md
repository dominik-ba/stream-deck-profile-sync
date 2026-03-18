# stream-deck-profile-sync

Synchronize your Elgato Stream Deck profiles and plugins across multiple computers.

## Overview

Stream Deck Profile Sync is a command-line tool that keeps your Elgato Stream
Deck profiles and plugins consistent across multiple machines. It works by
copying your profiles and plugins to a shared directory – for example a folder
managed by Dropbox, OneDrive, Google Drive, or any other cloud-storage tool –
and pulling them on other machines.

You are in full control of when syncing happens: run `push` to publish your
current profiles and plugins, and `pull` to apply the latest version on another
machine.

## Supported Platforms

| Platform | Status |
|----------|--------|
| macOS    | ✅ Supported |
| Windows  | ✅ Supported |
| Linux    | ❌ Not supported (Elgato Stream Deck software unavailable) |

> **Cross-platform plugin compatibility**: Plugins often contain platform-specific
> binaries (e.g. `.exe` files on Windows, `.app` bundles on macOS).  Syncing
> plugins between a Windows machine and a macOS machine will transfer the files
> but the plugins will not work on the other OS.  If you only sync between
> machines running the **same operating system** (e.g. multiple Windows PCs)
> plugin sync works perfectly.  Use `--no-plugins` to skip plugin sync when
> working across different operating systems.

## Installation

```bash
pip install stream-deck-profile-sync
```

## Quick Start

### 1. Choose a sync directory

Pick a folder that is already synced by your cloud-storage client, for example:

| Service | Example path |
|---------|--------------|
| Dropbox | `~/Dropbox/stream-deck-sync` |
| OneDrive | `~/OneDrive/stream-deck-sync` |
| Google Drive | `~/Google Drive/stream-deck-sync` |
| iCloud Drive | `~/Library/Mobile Documents/com~apple~CloudDocs/stream-deck-sync` |

### 2. Initialize on your primary machine

```bash
stream-deck-sync init ~/Dropbox/stream-deck-sync
```

### 3. Push your profiles and plugins

```bash
stream-deck-sync push
```

### 4. Pull on another machine

After the cloud-storage client has synced the files, run on the other machine:

```bash
stream-deck-sync init ~/Dropbox/stream-deck-sync
stream-deck-sync pull
```

Then restart the Stream Deck application to apply the new profiles.

## Commands

### `init`

Configure the sync directory (only needed once per machine).

```
stream-deck-sync init SYNC_DIR
```

`SYNC_DIR` is the path to your shared cloud-storage folder.

---

### `push`

Copy local profiles and plugins to the sync directory.

```
stream-deck-sync push [OPTIONS]

Options:
  -d, --sync-dir PATH      Sync directory (overrides configured value)
  -p, --profiles-dir PATH  Stream Deck profiles directory (auto-detected)
  --plugins-dir PATH       Stream Deck plugins directory (auto-detected)
  --no-plugins             Skip syncing plugins
```

---

### `pull`

Replace local profiles (and plugins) with the data from the sync directory.
Timestamped backups of your current profiles and plugins are created
automatically.

```
stream-deck-sync pull [OPTIONS]

Options:
  -d, --sync-dir PATH      Sync directory (overrides configured value)
  -p, --profiles-dir PATH  Stream Deck profiles directory (auto-detected)
  --plugins-dir PATH       Stream Deck plugins directory (auto-detected)
  --no-plugins             Skip syncing plugins
  --no-backup              Skip creating backups before pulling
```

---

### `status`

Show a human-readable diff between local and synced profiles and plugins.
Profile and plugin folders are shown by their **display name** (read from
`manifest.json`) rather than their internal GUID folder names.

```
stream-deck-sync status [OPTIONS]

Options:
  -d, --sync-dir PATH      Sync directory (overrides configured value)
  -p, --profiles-dir PATH  Stream Deck profiles directory (auto-detected)
  --plugins-dir PATH       Stream Deck plugins directory (auto-detected)
  --no-plugins             Skip comparing plugins
```

Example output:

```
Stream Deck Profile Sync Status
========================================
Last push: 2024-01-15T09:30:00+00:00

Profiles
--------
  Modified (1):
    ~ My Twitch Controls  [ABC123.sdProfile]
        · manifest.json
  Local only (1):
    + Gaming Profile  [NEW999.sdProfile]
        · manifest.json

  2 file(s) in sync

Plugins
-------
  Modified (1):
    ~ OBS Studio  [com.example.myplugin.sdPlugin]
        · manifest.json

  2 file(s) in sync
```

## How it Works

- **Profile and plugin location** is detected automatically from the standard
  Elgato installation paths (configurable via `--profiles-dir` /
  `--plugins-dir`).
- **Human-readable names** – the `status` command reads the `Name` field from
  each profile's and plugin's `manifest.json` so you see friendly display names
  instead of internal GUID folder names.
- **State tracking** – after every push, a `.stream-deck-sync-state.json` file
  is written to the sync directory. It records the timestamp and MD5 hash of
  every synced file so the `status` command can show exactly what has changed.
- **Backups** – `pull` always creates timestamped backup folders next to your
  profiles and plugins directories before overwriting anything (disable with
  `--no-backup`).
- **Tool configuration** is stored in `~/.stream-deck-sync/config.json`.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```
