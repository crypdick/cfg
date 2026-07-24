from __future__ import annotations

from collections.abc import Iterable

import typer


def echo_lines(lines: Iterable[str]) -> None:
    for line in lines:
        typer.echo(line)
