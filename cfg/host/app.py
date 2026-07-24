from __future__ import annotations

import typer

from cfg.core.typer_utils import echo_lines
from cfg.host.logic import api as logic

app = typer.Typer(add_completion=False, no_args_is_help=True)
features_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(features_app, name="feature")

# Typer option singletons (avoid B008: function call in argument defaults)
_INIT_FEATURES_OPT = typer.Option([], "--feature", help="Initial feature(s) (repeatable).")
_INIT_REPOS_OPT = typer.Option(
    [],
    "--repo",
    help="Register a repo checkout for this host: 'owner/repo=/abs/path' (repeatable).",
)
_CREATE_REQUIRES_OPT = typer.Option([], "--requires", help="Required feature(s) (repeatable).")


@app.command("current")
def current_host() -> None:
    """Show the current host identity for this machine."""
    echo_lines(logic.current_host())


@app.command()
def settings(host: str | None = typer.Argument(None)) -> None:
    """Show host settings (from inventory)."""
    echo_lines(logic.settings(host=host))


@app.command()
def apply(
    host: str | None = typer.Argument(None),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan mode: do not execute operations."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress verbose pyinfra output."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing non-link files with symlinks."),
) -> None:
    """Apply host configuration to the current machine (home scope)."""
    echo_lines(logic.apply(host=host, dry_run=dry_run, quiet=quiet, force=force))


@app.command("managed")
def managed(host: str | None = typer.Argument(None)) -> None:
    """Show managed files for a host (linked, mirrored, generated)."""
    echo_lines(logic.managed(host=host))


@app.command("mirror")
def mirror_path(
    path: str,
    host: str | None = typer.Option(None, "--host", help="Host name (defaults to current host)."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing managed payload in the personalization repository.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Mirror a home file/dir into cfg (copies into host-specific home payload)."""
    echo_lines(logic.add_path(path=path, host=host, force=force, dry_run=dry_run))


@app.command("unmirror")
def unmirror_path(
    path: str,
    host: str | None = typer.Option(None, "--host", help="Host name (defaults to current host)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Unmirror a managed home path from the personalization repository."""
    echo_lines(logic.remove_path(path=path, host=host, dry_run=dry_run))


@app.command("sync-repos")
def sync_repos(
    host: str | None = typer.Argument(None),
    fetch_only: bool = typer.Option(False, "--fetch-only", help="Only fetch; do not fast-forward pull."),
    remote: str = typer.Option("origin", "--remote", help="Remote name to fetch from (default: origin)."),
    allow_dirty: bool = typer.Option(
        False, "--allow-dirty", help="Allow pull/merge even if working tree is dirty."
    ),
    submodules: bool = typer.Option(False, "--submodules", help="Update submodules after syncing."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Plan mode: do not execute git operations (no fetch/merge/submodule update).",
    ),
) -> None:
    """Sync all repos listed in host inventory (fetch + ff-only update)."""
    echo_lines(
        logic.sync_repos(
            host=host,
            fetch_only=fetch_only,
            remote=remote,
            allow_dirty=allow_dirty,
            submodules=submodules,
            dry_run=dry_run,
        )
    )


@app.command("run")
def run_workflow(
    workflow: str,
    hosts: str = typer.Option(..., "--hosts", help="Host/group selector (name, group, or comma-separated)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan mode: do not execute operations."),
) -> None:
    """Run a host workflow (pyinfra deploy) against a host/group selector."""
    echo_lines(logic.run_workflow(workflow=workflow, hosts=hosts, dry_run=dry_run))


@app.command("debug-inventory")
def debug_inventory(
    hosts: str | None = typer.Option(
        None,
        "--hosts",
        help="Optional host/group selector (name, group, comma-separated). If omitted, shows all inventory hosts.",
    ),
    print_generated: bool = typer.Option(
        False,
        "--print",
        help="Print the generated runtime inventory.py to stdout (in addition to or instead of running pyinfra).",
    ),
    run: bool = typer.Option(
        True,
        "--run/--no-run",
        help="Run `pyinfra <inventory.py> debug-inventory` (default: run).",
    ),
) -> None:
    """Debug the runtime-generated pyinfra inventory (hosts, groups, and host.data)."""
    text = logic.debug_inventory(hosts=hosts, print_generated=print_generated, run=run)
    if text:
        typer.echo(text, nl=False)


@app.command("init")
def init_host(
    host: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
    features: list[str] = _INIT_FEATURES_OPT,
    repos: list[str] = _INIT_REPOS_OPT,
) -> None:
    """Create/update cfg inventory for a host."""
    try:
        lines = logic.init_host(host=host, dry_run=dry_run, features=features, repos=repos)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    echo_lines(lines)


@app.command("edit")
def edit_host(host: str) -> None:
    """Print the inventory path for a host."""
    typer.echo(str(logic.edit_host(host=host)))


@features_app.command("list")
def features_list(host: str | None = typer.Argument(None)) -> None:
    """List features for a host (from inventory)."""
    echo_lines(logic.features_list(host=host))


@features_app.command("add")
def features_add(
    feature: str,
    host: str | None = typer.Argument(None),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Add a feature to a host (writes to the host settings file)."""
    echo_lines(logic.features_add(feature=feature, host=host, dry_run=dry_run))


@features_app.command("remove")
def features_remove(
    feature: str,
    host: str | None = typer.Argument(None),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Remove a feature from a host (writes to the host settings file)."""
    echo_lines(logic.features_remove(feature=feature, host=host, dry_run=dry_run))


@features_app.command("create")
def features_create(
    feature: str,
    requires: list[str] = _CREATE_REQUIRES_OPT,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not create files."),
) -> None:
    """Create a feature directory with a feature.toml scaffold."""
    echo_lines(logic.features_create(feature=feature, requires=requires, dry_run=dry_run))


@features_app.command("delete")
def features_delete(
    feature: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not delete files."),
) -> None:
    """Delete a feature directory (checks that no hosts are using it first)."""
    echo_lines(logic.features_delete(feature=feature, dry_run=dry_run))
