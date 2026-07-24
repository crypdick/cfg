from __future__ import annotations

from pathlib import Path

import typer

from cfg.core.typer_utils import echo_lines
from cfg.repo.logic import api as logic

app = typer.Typer(add_completion=False, no_args_is_help=True)
features_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(features_app, name="feature")

# Typer option singletons (avoid B008: function call in argument defaults)
_INIT_REPO_FEATURES_OPT = typer.Option([], "--feature", help="Initial feature(s) (repeatable).")


@app.command("init")
def init_repo(
    host: str | None = typer.Option(
        None,
        "--host",
        help="Host name to register this repo under (defaults to current host hint).",
    ),
    features: list[str] = _INIT_REPO_FEATURES_OPT,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files or attach."),
) -> None:
    """Register this repo in the personalization inventory and attach it to the current host."""
    echo_lines(logic.init_repo(host=host, features=features, dry_run=dry_run))


@app.command()
def settings() -> None:
    """Show repo settings (from inventory + local attachment state)."""
    echo_lines(logic.settings())


@features_app.command("list")
def features_list() -> None:
    """List features for this repo (from inventory)."""
    echo_lines(logic.features_list())


@features_app.command("add")
def features_add(
    feature: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Add a feature to this repo (writes to the repo settings file)."""
    echo_lines(logic.features_add(feature=feature, dry_run=dry_run))


@features_app.command("remove")
def features_remove(
    feature: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Remove a feature from this repo (writes to the repo settings file)."""
    echo_lines(logic.features_remove(feature=feature, dry_run=dry_run))


@app.command()
def apply(
    allow_dirty: bool = typer.Option(
        False, "--allow-dirty", help="Allow overlays even if the repo is dirty."
    ),
    ensure_host: bool = typer.Option(
        False,
        "--ensure-host",
        help="Opt-in: ensure missing host prerequisites implied by repo owners (runs host workflow on @local).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan mode: do not execute operations."),
) -> None:
    """Apply cfg repo configuration (attach + overlays + generated artifacts + managed mirror files)."""
    echo_lines(logic.apply(allow_dirty=allow_dirty, ensure_host=ensure_host, dry_run=dry_run))


@app.command("link")
def link(
    path: str,
    feature: str = typer.Option(
        ...,
        "--feature",
        help="Feature name to link into (payload under features/repo/<feature>/overlay).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Move a repo file into a feature payload overlay and link the repo path."""
    dest = logic.link(path=Path(path), feature=feature, dry_run=dry_run)
    if dry_run:
        typer.echo(str(dest))
    else:
        typer.echo(f"linked to: {dest}")


@app.command("unlink")
def unlink(
    path: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Unlink a repo file by replacing the symlink with a real file (keeps the overlay payload)."""
    dest = logic.unlink(path=Path(path), dry_run=dry_run)
    if dry_run:
        typer.echo(str(dest))
    else:
        typer.echo(f"unlinked (was pointing to): {dest}")


@app.command("mirror")
def mirror_path(
    path: str,
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing managed payload in the personalization repository.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Mirror a repo file/dir into cfg (copies into repo-specific mirror payload)."""
    echo_lines(logic.add_path(path=path, force=force, dry_run=dry_run))


@app.command("unmirror")
def unmirror_path(
    path: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions but do not write files."),
) -> None:
    """Unmirror a managed repo file or directory from the personalization repository."""
    echo_lines(logic.remove_path(path=path, dry_run=dry_run))


@app.command()
def check(staged: bool = typer.Option(False, "--staged", help="Check staged content (for hooks).")) -> None:
    """Check managed artifacts for drift and print remediation guidance."""
    # Intentionally quiet; underlying check prints guidance as needed.
    logic.check(staged=staged)
