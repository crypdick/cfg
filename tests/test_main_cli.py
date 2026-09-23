from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cfg.core.errors import CfgError


def test_version_command() -> None:
    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["version"])
    assert res.exit_code == 0
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert res.output == f"cfg {project['project']['version']}\n"


def test_main_wraps_cfgerror_into_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import main

    monkeypatch.setattr(main, "app", lambda: (_ for _ in ()).throw(CfgError("boom")))
    with pytest.raises(SystemExit) as e:
        main.main()
    assert e.value.code == 1


def test_init_wizard_removed() -> None:
    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["init"])
    # Click uses exit code 2 for usage errors like unknown commands.
    assert res.exit_code == 2, (res.output, res.exception)
    assert "No such command" in res.output
