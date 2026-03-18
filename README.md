# stream-deck-profile-sync

Synchronize your Elgato Stream Deck profiles across multiple computers.

## Overview

Stream Deck Profile Sync is a command-line tool that keeps your Elgato Stream
Deck profiles consistent across multiple machines. It works by copying your
profiles to a shared directory – for example a folder managed by Dropbox,
OneDrive, Google Drive, or any other cloud-storage tool – and pulling them on
other machines.

You are in full control of when syncing happens: run `push` to publish your
current profiles, and `pull` to apply the latest version on another machine.

## Supported Platforms

| Platform | Status |
|----------|--------|
| macOS    | ✅ Supported |
| Windows  | ✅ Supported |
| Linux    | ❌ Not supported (Elgato Stream Deck software unavailable) |

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

### 3. Push your profiles

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

Copy local profiles to the sync directory.

```
stream-deck-sync push [OPTIONS]

Options:
  -d, --sync-dir PATH      Sync directory (overrides configured value)
  -p, --profiles-dir PATH  Stream Deck profiles directory (auto-detected)
```

---

### `pull`

Replace local profiles with the profiles from the sync directory. A
timestamped backup of your current profiles is created automatically.

```
stream-deck-sync pull [OPTIONS]

Options:
  -d, --sync-dir PATH      Sync directory (overrides configured value)
  -p, --profiles-dir PATH  Stream Deck profiles directory (auto-detected)
  --no-backup              Skip creating a backup before pulling
```

---

### `status`

Show a diff between local profiles and the synced profiles.

```
stream-deck-sync status [OPTIONS]

Options:
  -d, --sync-dir PATH      Sync directory (overrides configured value)
  -p, --profiles-dir PATH  Stream Deck profiles directory (auto-detected)
```

Example output:

```
Stream Deck Profile Sync Status
========================================
Last push: 2024-01-15T09:30:00+00:00

Modified (1):
  ~ ABC123.sdProfile/manifest.json
Local only (1):
  + NEW.sdProfile/manifest.json

3 file(s) in sync
```

## How it Works

- **Profile location** is detected automatically from the standard Elgato
  installation paths (configurable via `--profiles-dir`).
- **State tracking** – after every push, a `.stream-deck-sync-state.json`
  file is written to the sync directory. It records the timestamp and MD5
  hash of every synced file so the `status` command can show exactly what
  has changed.
- **Backups** – `pull` always creates a timestamped backup folder next to
  your profiles directory before overwriting anything (disable with
  `--no-backup`).
- **Tool configuration** is stored in `~/.stream-deck-sync/config.json`.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```
