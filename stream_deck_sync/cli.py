"""Command-line interface for stream-deck-sync."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from . import __version__
from . import config as config_module
from . import profiles as profiles_module
from . import sync as sync_module


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """Stream Deck Profile Sync – synchronize profiles across multiple machines.

    Works with any cloud storage that syncs a local folder (Dropbox, OneDrive,
    Google Drive, iCloud Drive, …). Configure the sync directory once with
    'init', then use 'push' and 'pull' to keep profiles in sync.
    """


@cli.command()
@click.argument("sync_dir", type=click.Path(path_type=Path))
def init(sync_dir: Path) -> None:
    """Configure the sync directory.

    SYNC_DIR is the path to your shared cloud storage folder where profiles
    will be stored (e.g. ~/Dropbox/stream-deck-sync).
    """
    sync_path = sync_dir.resolve()
    sync_path.mkdir(parents=True, exist_ok=True)
    config_module.set_sync_dir(sync_path)
    click.echo(f"✓ Sync directory configured: {sync_path}")
    click.echo(
        "\nNext steps:"
        "\n  1. Run 'stream-deck-sync push' to push your current profiles"
        "\n  2. On another machine run 'stream-deck-sync pull' to apply them"
    )


@cli.command()
@click.option(
    "--sync-dir",
    "-d",
    type=click.Path(path_type=Path),
    default=None,
    help="Sync directory path (overrides configured value).",
)
@click.option(
    "--profiles-dir",
    "-p",
    type=click.Path(path_type=Path),
    default=None,
    help="Stream Deck profiles directory (auto-detected if not provided).",
)
def push(sync_dir: Optional[Path], profiles_dir: Optional[Path]) -> None:
    """Push local Stream Deck profiles to the sync directory.

    Copies all profiles to the sync directory so they can be pulled on
    other machines. Any previously synced profiles are replaced.
    """
    sync_path = _resolve_sync_dir(sync_dir)
    profiles_path = _resolve_profiles_dir(profiles_dir)

    click.echo(f"Pushing profiles from {profiles_path}")
    click.echo(f"  → {sync_path}")

    try:
        state = sync_module.push(profiles_path, sync_path)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc))

    file_count = len(state.get("profiles_state", {}))
    click.echo(f"✓ Pushed {file_count} file(s)")
    click.echo(f"  Last push: {state['last_push']}")


@cli.command()
@click.option(
    "--sync-dir",
    "-d",
    type=click.Path(path_type=Path),
    default=None,
    help="Sync directory path (overrides configured value).",
)
@click.option(
    "--profiles-dir",
    "-p",
    type=click.Path(path_type=Path),
    default=None,
    help="Stream Deck profiles directory (auto-detected if not provided).",
)
@click.option(
    "--no-backup",
    is_flag=True,
    default=False,
    help="Skip creating a backup of local profiles before pulling.",
)
def pull(
    sync_dir: Optional[Path],
    profiles_dir: Optional[Path],
    no_backup: bool,
) -> None:
    """Pull Stream Deck profiles from the sync directory.

    Replaces local profiles with the ones from the sync directory.
    A timestamped backup of the current local profiles is created by default.

    Restart the Stream Deck application after pulling to apply the new profiles.
    """
    sync_path = _resolve_sync_dir(sync_dir)
    profiles_path = _resolve_profiles_dir(profiles_dir)

    click.echo(f"Pulling profiles from {sync_path}")
    click.echo(f"  → {profiles_path}")

    try:
        state, backup_dir = sync_module.pull(
            profiles_path, sync_path, backup=not no_backup
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc))

    click.echo("✓ Profiles pulled successfully")
    if backup_dir:
        click.echo(f"  Backup saved at: {backup_dir}")
    click.echo(
        "\nRestart the Stream Deck application to apply the new profiles."
    )


@cli.command()
@click.option(
    "--sync-dir",
    "-d",
    type=click.Path(path_type=Path),
    default=None,
    help="Sync directory path (overrides configured value).",
)
@click.option(
    "--profiles-dir",
    "-p",
    type=click.Path(path_type=Path),
    default=None,
    help="Stream Deck profiles directory (auto-detected if not provided).",
)
def status(sync_dir: Optional[Path], profiles_dir: Optional[Path]) -> None:
    """Show the sync status comparing local and synced profiles."""
    sync_path = _resolve_sync_dir(sync_dir)
    profiles_path = _resolve_profiles_dir(profiles_dir)

    result = sync_module.status(profiles_path, sync_path)

    click.echo("Stream Deck Profile Sync Status")
    click.echo("=" * 40)

    if result["last_push"]:
        click.echo(f"Last push: {result['last_push']}")
    if result["last_pull"]:
        click.echo(f"Last pull: {result['last_pull']}")

    if not result["has_local"]:
        click.echo("\n⚠  Local profiles directory not found.")
    if not result["has_sync"]:
        click.echo("\n⚠  No synced profiles found. Run 'push' first.")
        return

    click.echo()

    total_changes = (
        len(result["modified"])
        + len(result["local_only"])
        + len(result["sync_only"])
    )

    if total_changes == 0:
        click.echo("✓ All files are in sync")
    else:
        if result["modified"]:
            click.echo(f"Modified ({len(result['modified'])}):")
            for f in result["modified"]:
                click.echo(f"  ~ {f}")
        if result["local_only"]:
            click.echo(f"Local only ({len(result['local_only'])}):")
            for f in result["local_only"]:
                click.echo(f"  + {f}")
        if result["sync_only"]:
            click.echo(f"Sync only ({len(result['sync_only'])}):")
            for f in result["sync_only"]:
                click.echo(f"  - {f}")

    if result["in_sync"]:
        click.echo(f"\n{len(result['in_sync'])} file(s) in sync")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_sync_dir(sync_dir_arg: Optional[Path]) -> Path:
    """Return the sync directory from the CLI argument or saved config."""
    if sync_dir_arg is not None:
        return sync_dir_arg.resolve()
    sync_path = config_module.get_sync_dir()
    if sync_path is None:
        raise click.UsageError(
            "No sync directory configured.\n"
            "Run 'stream-deck-sync init <path>' to configure one, "
            "or provide --sync-dir."
        )
    return sync_path


def _resolve_profiles_dir(profiles_dir_arg: Optional[Path]) -> Path:
    """Return the profiles directory from the CLI argument or auto-detection."""
    if profiles_dir_arg is not None:
        return profiles_dir_arg.resolve()
    try:
        return profiles_module.get_profiles_dir()
    except RuntimeError as exc:
        raise click.UsageError(str(exc))
