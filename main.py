from __future__ import annotations

from importlib.metadata import version as package_version

import typer

from cfg.core.context import CfgContext
from cfg.core.errors import CfgError
from cfg.core.validation import validate_configuration
from cfg.host.app import app as host_app
from cfg.repo.app import app as repo_app

app = typer.Typer(
    # Enable Typer/Click shell completion helpers (zsh/bash/fish).
    no_args_is_help=True,
)

app.add_typer(repo_app, name="repo")
app.add_typer(host_app, name="host")


@app.command()
def version() -> None:
    """Print version info."""
    typer.echo(f"cfg {package_version('cfg')}")


@app.command()
def validate() -> None:
    """Validate the complete personalization repository without writing."""
    report = validate_configuration(CfgContext.load().root)
    for line in report.lines():
        typer.echo(line)


def main() -> None:
    try:
        app()
    except CfgError as e:
        # Keep errors user-friendly by default.
        typer.echo(str(e), err=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
