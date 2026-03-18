# GitHub Copilot Instructions

## Project Overview

**stream-deck-profile-sync** is a Python CLI tool that synchronizes Elgato Stream Deck profiles and plugins across multiple computers using any cloud storage that syncs a local folder (Dropbox, OneDrive, Google Drive, iCloud Drive, etc.). Users manually control when to push/pull; the tool never runs automatically.

## Repository Structure

```
stream-deck-profile-sync/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI (Python 3.9–3.12)
├── stream_deck_sync/           # Main source package
│   ├── __init__.py             # Package version (__version__)
│   ├── cli.py                  # Click CLI commands (init, push, pull, status)
│   ├── config.py               # Config file management (~/.stream-deck-sync/config.json)
│   ├── profiles.py             # OS-specific Stream Deck path detection
│   └── sync.py                 # Core sync logic (push, pull, status, state tracking)
├── tests/
│   ├── test_cli.py             # CLI integration tests (Click test runner)
│   ├── test_config.py          # Config read/write tests
│   ├── test_profiles.py        # Platform path detection tests
│   └── test_sync.py            # Core sync logic tests
├── pyproject.toml              # Project metadata, dependencies, pytest config
├── README.md
└── CHANGELOG.md                # Keep a Changelog format
```

## Technology Stack

- **Language:** Python 3.9+
- **CLI framework:** [Click](https://click.palletsprojects.com/) 8.0+
- **Build system:** setuptools with `pyproject.toml` (PEP 517/518)
- **Testing:** pytest 7.0+ with pytest-cov
- **CI:** GitHub Actions (matrix across Python 3.9, 3.10, 3.11, 3.12 on ubuntu-latest)
- **Supported platforms:** Windows and macOS only (Linux raises `RuntimeError`)
- **Package entry point:** `stream-deck-sync` → `stream_deck_sync.cli:cli`

## Key Architecture Concepts

### Profiles and Plugins
- **Profiles** (`*.sdProfile` folders): Stream Deck button layout profiles, stored in platform-specific directories detected by `profiles.get_profiles_dir()`.
- **Plugins** (`*.sdPlugin` folders): Stream Deck plugins, detected by `profiles.get_plugins_dir()`. Plugins contain OS-specific binaries, so cross-platform use is warned about.
- Each profile/plugin folder contains a `manifest.json` with a `"Name"` key used for human-readable display.

### Sync State
- `sync.push()` and `sync.pull()` write a state file (`.stream-deck-sync-state.json`) in the sync directory.
- State tracks MD5 hashes and timestamps for all synced files, enabling `sync.status()` to detect what has changed.
- State keys: `"profiles"`, `"plugins"`, each containing `{"synced_at": ISO8601, "files": {"relative/path": "md5hex"}}`.

### Configuration
- Config is stored at `~/.stream-deck-sync/config.json` with a single `"sync_dir"` key.
- `config.py` provides `get_sync_dir()` / `set_sync_dir()` helpers.

### Backup
- Before `pull`, a timestamped backup of the current local profiles/plugins directory is created (can be skipped with `--no-backup`).

## Code Style and Conventions

- **`from __future__ import annotations`** at the top of every source file (enables PEP 563 postponed evaluation of annotations).
- **Type hints** on all function signatures; use `dict[str, str]` / `list[str]` (lowercase) not `Dict`/`List` from `typing`.
- Use `Optional[X]` from `typing` for optional parameters (compatible with Python 3.9).
- **Docstrings:** Google-style with `Args:` and `Returns:` sections on public functions.
- **PEP 8** formatting; 4-space indentation; max line length ~88 characters.
- Import order: stdlib → third-party → local (relative imports with `from . import ...`).
- Use `pathlib.Path` for all file system operations; avoid `os.path`.
- Raise `click.ClickException` (not `SystemExit`) for user-facing CLI errors in `cli.py`.
- Raise `RuntimeError` for unsupported platforms or unrecoverable errors in library code.

## Testing Practices

- Use `pytest` fixtures; prefer `tmp_path` (built-in pytest fixture) for temporary directories.
- Tests create realistic fake directory structures (e.g., `.sdProfile` and `.sdPlugin` folders with `manifest.json`) rather than mocking the file system.
- Mock only external state (e.g., config file path, platform detection) using `monkeypatch`.
- Use `click.testing.CliRunner` for CLI command tests.
- Each test module starts with `"""Tests for stream_deck_sync.<module> module."""`.
- Fixtures are grouped under a `# Fixtures` section comment; helper factories use `make_*` naming.

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=stream_deck_sync
```

## Development Workflow

```bash
# Set up a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run the CLI locally
stream-deck-sync --help
```

## CI/CD

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push to `main` and on every pull request. It:
1. Tests against Python 3.9, 3.10, 3.11, and 3.12.
2. Installs the package with `pip install -e ".[dev]"`.
3. Runs `pytest --cov=stream_deck_sync`.

`fail-fast: false` is set so all matrix versions run even if one fails.

## Adding New Features

- New CLI commands belong in `cli.py` as `@cli.command()` functions.
- Core file system logic belongs in `sync.py`.
- Platform-specific path detection belongs in `profiles.py`.
- Config changes belong in `config.py`.
- Add corresponding tests in the matching `tests/test_<module>.py` file.
- Update `CHANGELOG.md` under `[Unreleased]` following the Keep a Changelog format.
