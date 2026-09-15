from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from cfg.core.state import read_host_state

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    import pytest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    cfg_root = tmp_path / "cfg"
    _write(cfg_root / ".cfg-root", "")
    _write(
        cfg_root / "features/host/base/feature.toml",
        "schema_version = 1\nrequires = []\nconflicts = []\ngenerated = []\n",
    )
    _write(cfg_root / "hosts/h1/cfg.toml", 'name = "h1"\nfeatures = []\n')
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return cfg_root, home


def test_host_apply_threads_runner_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_host(tmp_path, monkeypatch)

    import cfg.host.logic.apply as host_apply_logic
    import main

    called: dict[str, Any] = {}
    monkeypatch.setattr(host_apply_logic, "run_pyinfra", lambda **kwargs: called.update(kwargs))
    result = CliRunner().invoke(main.app, ["host", "apply", "h1", "-y"])

    assert result.exit_code == 0, (result.output, result.exception)
    assert "home applied." in result.output
    assert called["current_host_for_local"] == "h1"
    assert called["dry_run"] is False
    assert called["auto_approve"] is True


def test_host_apply_dry_run_passes_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_host(tmp_path, monkeypatch)

    import cfg.host.logic.apply as host_apply_logic
    import main

    called: dict[str, Any] = {}
    monkeypatch.setattr(host_apply_logic, "run_pyinfra", lambda **kwargs: called.update(kwargs))
    result = CliRunner().invoke(main.app, ["host", "apply", "h1", "--dry-run"])

    assert result.exit_code == 0, (result.output, result.exception)
    assert called["dry_run"] is True


def test_host_apply_records_state_only_after_successful_deploy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root, home = _setup_host(tmp_path, monkeypatch)
    _write(
        cfg_root / "features/host/base/feature.toml",
        'schema_version = 1\nrequires = []\nconflicts = []\ngenerated = ["generated"]\n',
    )
    _write(cfg_root / "features/host/base/deploy.py", "def main():\n    pass\n")
    import cfg.host.logic.apply as host_apply_logic
    import main

    def fail_deploy(**_kwargs: Any) -> None:
        raise RuntimeError("deploy failed")

    runner = CliRunner()
    monkeypatch.setattr(host_apply_logic, "run_pyinfra", fail_deploy)
    failed = runner.invoke(main.app, ["host", "apply", "h1"])
    assert failed.exit_code != 0
    assert read_host_state().managed == {}

    def successful_deploy(**_kwargs: Any) -> None:
        _write(home / "generated", "deployed\n")

    monkeypatch.setattr(host_apply_logic, "run_pyinfra", successful_deploy)
    succeeded = runner.invoke(main.app, ["host", "apply", "h1"])
    assert succeeded.exit_code == 0, (succeeded.output, succeeded.exception)
    assert read_host_state().managed["generated"].kind == "generated"
