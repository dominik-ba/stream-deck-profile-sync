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
@click.option(
    "--plugins-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Stream Deck plugins directory (auto-detected if not provided).",
)
@click.option(
    "--no-plugins",
    is_flag=True,
    default=False,
    help="Skip syncing plugins.",
)
@click.option(
    "--exclude",
    multiple=True,
    metavar="PATTERN",
    help=(
        "Additional filename pattern to exclude from syncing "
        "(e.g. '*.tmp').  May be specified multiple times.  "
        "The built-in defaults (*.log) are always applied."
    ),
)
def push(
    sync_dir: Optional[Path],
    profiles_dir: Optional[Path],
    plugins_dir: Optional[Path],
    no_plugins: bool,
    exclude: tuple[str, ...],
) -> None:
    """Push local Stream Deck profiles and plugins to the sync directory.

    Copies all profiles (and plugins unless --no-plugins is set) to the sync
    directory so they can be pulled on other machines. Any previously synced
    data is replaced.
    """
    sync_path = _resolve_sync_dir(sync_dir)
    profiles_path = _resolve_profiles_dir(profiles_dir)
    plugins_path = None if no_plugins else _resolve_plugins_dir_optional(plugins_dir)

    click.echo(f"Pushing profiles from {profiles_path}")
    if plugins_path:
        click.echo(f"Pushing plugins from {plugins_path}")
    click.echo(f"  → {sync_path}")

    exclude_patterns = list(sync_module.DEFAULT_EXCLUDE_PATTERNS) + list(exclude)
    try:
        state = sync_module.push(
            profiles_path,
            sync_path,
            plugins_dir=plugins_path,
            exclude_patterns=exclude_patterns,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc))

    profile_count = len(state.get("profiles_state", {}))
    click.echo(f"✓ Pushed {profile_count} profile file(s)")
    if "plugins_state" in state:
        plugin_count = len(state["plugins_state"])
        click.echo(f"✓ Pushed {plugin_count} plugin file(s)")
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
    "--plugins-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Stream Deck plugins directory (auto-detected if not provided).",
)
@click.option(
    "--no-plugins",
    is_flag=True,
    default=False,
    help="Skip syncing plugins.",
)
@click.option(
    "--no-backup",
    is_flag=True,
    default=False,
    help="Skip creating a backup of local data before pulling.",
)
def pull(
    sync_dir: Optional[Path],
    profiles_dir: Optional[Path],
    plugins_dir: Optional[Path],
    no_plugins: bool,
    no_backup: bool,
) -> None:
    """Pull Stream Deck profiles and plugins from the sync directory.

    Replaces local profiles (and plugins unless --no-plugins is set) with the
    ones from the sync directory. Timestamped backups of the current local data
    are created by default.

    Restart the Stream Deck application after pulling to apply the new profiles.
    """
    sync_path = _resolve_sync_dir(sync_dir)
    profiles_path = _resolve_profiles_dir(profiles_dir)
    plugins_path = None if no_plugins else _resolve_plugins_dir_optional(plugins_dir)

    click.echo(f"Pulling profiles from {sync_path}")
    click.echo(f"  → {profiles_path}")
    if plugins_path:
        click.echo(f"  → {plugins_path} (plugins)")

    try:
        state, profiles_backup, plugins_backup = sync_module.pull(
            profiles_path, sync_path, backup=not no_backup, plugins_dir=plugins_path
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc))

    click.echo("✓ Profiles pulled successfully")
    if profiles_backup:
        click.echo(f"  Profiles backup saved at: {profiles_backup}")
    if plugins_backup:
        click.echo(f"  Plugins backup saved at: {plugins_backup}")
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
@click.option(
    "--plugins-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Stream Deck plugins directory (auto-detected if not provided).",
)
@click.option(
    "--no-plugins",
    is_flag=True,
    default=False,
    help="Skip comparing plugins.",
)
@click.option(
    "--exclude",
    multiple=True,
    metavar="PATTERN",
    help=(
        "Additional filename pattern to exclude from comparison "
        "(e.g. '*.tmp').  May be specified multiple times.  "
        "The built-in defaults (*.log) are always applied."
    ),
)
def status(
    sync_dir: Optional[Path],
    profiles_dir: Optional[Path],
    plugins_dir: Optional[Path],
    no_plugins: bool,
    exclude: tuple[str, ...],
) -> None:
    """Show the sync status comparing local and synced profiles and plugins."""
    sync_path = _resolve_sync_dir(sync_dir)
    profiles_path = _resolve_profiles_dir(profiles_dir)
    plugins_path = None if no_plugins else _resolve_plugins_dir_optional(plugins_dir)

    exclude_patterns = list(sync_module.DEFAULT_EXCLUDE_PATTERNS) + list(exclude)
    result = sync_module.status(
        profiles_path,
        sync_path,
        plugins_dir=plugins_path,
        exclude_patterns=exclude_patterns,
    )

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
        if not result["has_local"]:
            return

    # ---- Profiles section -----------------------------------------------
    click.echo("\nProfiles")
    click.echo("-" * 8)
    _print_section_changes(
        result["modified"],
        result["local_only"],
        result["sync_only"],
        result["in_sync"],
        base_local=profiles_path,
        base_sync=sync_path / sync_module.PROFILES_SUBDIR,
    )

    # ---- Plugins section ------------------------------------------------
    if plugins_path is not None:
        click.echo("\nPlugins")
        click.echo("-" * 7)
        if not result["has_sync_plugins"]:
            click.echo("  ⚠  No synced plugins found. Run 'push' first.")
        if result["has_local_plugins"] or result["has_sync_plugins"]:
            _print_section_changes(
                result["plugins_modified"],
                result["plugins_local_only"],
                result["plugins_sync_only"],
                result["plugins_in_sync"],
                base_local=plugins_path,
                base_sync=sync_path / sync_module.PLUGINS_SUBDIR,
            )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _print_section_changes(
    modified: list[str],
    local_only: list[str],
    sync_only: list[str],
    in_sync: list[str],
    base_local: Path,
    base_sync: Path,
) -> None:
    """Print a human-readable diff section (profiles or plugins)."""
    total_changes = len(modified) + len(local_only) + len(sync_only)

    if total_changes == 0:
        click.echo(f"  ✓ All {len(in_sync)} item(s) are in sync")
        return

    if modified:
        click.echo(f"  Modified ({len(_group_names(modified))}):")
        for folder, files in _group_names(modified).items():
            name = sync_module.read_manifest_name(base_local, folder)
            _print_item("~", name, folder, files)

    if local_only:
        click.echo(f"  Local only ({len(_group_names(local_only))}):")
        for folder, files in _group_names(local_only).items():
            name = sync_module.read_manifest_name(base_local, folder)
            _print_item("+", name, folder, files)

    if sync_only:
        click.echo(f"  Sync only ({len(_group_names(sync_only))}):")
        for folder, files in _group_names(sync_only).items():
            name = sync_module.read_manifest_name(base_sync, folder)
            _print_item("-", name, folder, files)

    if in_sync:
        click.echo(f"\n  {len(in_sync)} file(s) in sync")


def _group_names(file_paths: list[str]) -> dict[str, list[str]]:
    """Thin wrapper around sync_module._group_by_top_dir."""
    return sync_module._group_by_top_dir(file_paths)


def _print_item(
    marker: str, name: str, folder: str, files: list[str]
) -> None:
    """Print one profile/plugin entry with its changed files."""
    if name != folder:
        click.echo(f"    {marker} {name}  [{folder}]")
    else:
        click.echo(f"    {marker} {folder}")
    for f in files:
        if f:
            click.echo(f"        · {f}")


# ---------------------------------------------------------------------------
# Path resolution helpers
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


def _resolve_plugins_dir_optional(plugins_dir_arg: Optional[Path]) -> Optional[Path]:
    """Return the plugins directory, or None if it cannot be determined.

    Unlike the profiles directory, a missing plugins directory is not fatal –
    the caller can simply skip plugin sync in that case.
    """
    if plugins_dir_arg is not None:
        return plugins_dir_arg.resolve()
    try:
        return profiles_module.get_plugins_dir()
    except RuntimeError:
        return None

