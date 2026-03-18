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

## Prerequisites

- **Python 3.9 or newer** – check your version with:

  ```bash
  python --version
  # or on some systems:
  python3 --version
  ```

  If Python is not installed or the version is too old, download it from
  [python.org](https://www.python.org/downloads/) (Windows / macOS) or install
  it via your system package manager (Linux).

- **pip** – Python's package installer, bundled with Python 3.4+.  Upgrade it
  with:

  ```bash
  python -m pip install --upgrade pip
  ```

## Installation

> **Note:** This package is not yet published on PyPI.  Install it directly
> from GitHub using one of the methods below.

### Option A – pipx (recommended for end users)

[`pipx`](https://pipx.pypa.io/) installs Python command-line tools into their
own isolated environment so they never conflict with other packages.  It is the
modern, recommended way to install CLI tools.

1. Install `pipx` (one-time setup):

   ```bash
   # macOS (Homebrew)
   brew install pipx
   pipx ensurepath

   # Windows (in an elevated PowerShell / terminal)
   python -m pip install --user pipx
   python -m pipx ensurepath

   # After running ensurepath, open a new terminal so the PATH change takes effect.
   ```

2. Install stream-deck-profile-sync:

   ```bash
   pipx install git+https://github.com/dominik-ba/stream-deck-profile-sync.git
   ```

3. Verify the installation:

   ```bash
   stream-deck-sync --version
   ```

### Option B – pip inside a virtual environment

If you prefer a plain `pip` install, use a **virtual environment** to keep the
tool isolated from your system Python and other projects.

**macOS / Linux**

```bash
python3 -m venv ~/.venvs/stream-deck-sync
source ~/.venvs/stream-deck-sync/bin/activate
pip install git+https://github.com/dominik-ba/stream-deck-profile-sync.git
```

**Windows (Command Prompt)**

```bat
python -m venv %USERPROFILE%\.venvs\stream-deck-sync
%USERPROFILE%\.venvs\stream-deck-sync\Scripts\activate.bat
pip install git+https://github.com/dominik-ba/stream-deck-profile-sync.git
```

**Windows (PowerShell)**

```powershell
python -m venv $HOME\.venvs\stream-deck-sync
$HOME\.venvs\stream-deck-sync\Scripts\Activate.ps1
pip install git+https://github.com/dominik-ba/stream-deck-profile-sync.git
```

> **Tip – re-activating the environment**: When you open a new terminal you
> need to activate the virtual environment again with the `activate` command
> above before using `stream-deck-sync`.  With `pipx` (Option A) you never
> need to do this – the tool is always available.

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

### 1. Clone the repository

```bash
git clone https://github.com/dominik-ba/stream-deck-profile-sync.git
cd stream-deck-profile-sync
```

### 2. Create and activate a virtual environment

Using a virtual environment ensures the project's dependencies are isolated from
your system Python.  Python's built-in `venv` module is all you need.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (Command Prompt)**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Your terminal prompt will change (e.g. `(.venv) $`) to show the environment is
active.  All `pip` and `python` commands now use the isolated environment.

### 3. Install in editable mode with dev dependencies

```bash
pip install -e ".[dev]"
```

The `-e` flag (editable / "development" install) means changes you make to the
source code take effect immediately without reinstalling.  The `[dev]` extra
pulls in testing tools.

### 4. Run the tests

```bash
pytest
```

Or with a coverage report:

```bash
pytest --cov=stream_deck_sync
```

### 5. Deactivate the environment

When you are done, deactivate the virtual environment:

```bash
deactivate
```

### Notes on virtual environment tooling

Python has several options for managing virtual environments:

| Tool | Summary |
|------|---------|
| `venv` | Built into Python 3.3+.  No installation needed.  Recommended for development. |
| `pipx` | Best for *installing* CLI tools globally without polluting the system Python. |
| `pipenv` | Combines `pip` + `venv` with a `Pipfile`; less commonly used now. |
| `uv` | Modern, very fast drop-in replacement for `pip` + `venv`; increasingly popular. |
| `conda` | Geared towards data science; overkill for a simple CLI tool. |

For most contributors, `venv` (step 2 above) is the right choice.  If you want
even faster installs you can replace `pip install` with `uv pip install` after
[installing uv](https://github.com/astral-sh/uv).
