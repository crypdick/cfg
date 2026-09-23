from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from cfg.core.state import read_host_state

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    import cfg.host.logic.apply as host_apply_logic

    monkeypatch.setattr(host_apply_logic, "sync_apply_root", lambda *_args, **_kwargs: "up-to-date")
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


def test_host_apply_stops_before_deploy_when_sync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_host(tmp_path, monkeypatch)

    import cfg.host.logic.apply as host_apply_logic
    import main
    from cfg.core.errors import CfgError

    def fail_sync(*_args: Any, **_kwargs: Any) -> str:
        raise CfgError("Personalization repo is dirty")

    monkeypatch.setattr(host_apply_logic, "sync_apply_root", fail_sync)
    monkeypatch.setattr(
        host_apply_logic,
        "run_pyinfra",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("pyinfra should not run")),
    )
    result = CliRunner().invoke(main.app, ["host", "apply", "h1"])
    assert isinstance(result.exception, CfgError)
    assert "dirty" in str(result.exception)


def test_interactive_host_apply_refreshes_sudo_before_pyinfra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_host(tmp_path, monkeypatch)

    import subprocess
    import sys

    import cfg.host.logic.apply as host_apply_logic

    sudo_calls: list[list[str]] = []
    runner_called = False

    class _Result:
        returncode = 0

    def fake_subprocess_run(command: list[str], **_kwargs: Any) -> _Result:
        sudo_calls.append(command)
        return _Result()

    def fake_pyinfra(**_kwargs: Any) -> None:
        nonlocal runner_called
        runner_called = True

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(host_apply_logic.shutil, "which", lambda _command: "/usr/bin/sudo")
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(host_apply_logic, "run_pyinfra", fake_pyinfra)
    result = host_apply_logic.apply(host="h1", dry_run=False)

    assert result[-1] == "home applied."
    assert sudo_calls == [["sudo", "-v"]]
    assert runner_called


def test_failed_sudo_refresh_aborts_before_pyinfra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_host(tmp_path, monkeypatch)

    import subprocess
    import sys

    import cfg.host.logic.apply as host_apply_logic
    from cfg.core.errors import CfgError

    class _Result:
        returncode = 1

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(host_apply_logic.shutil, "which", lambda _command: "/usr/bin/sudo")
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: _Result())
    monkeypatch.setattr(
        host_apply_logic,
        "run_pyinfra",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("pyinfra should not run")),
    )
    with pytest.raises(CfgError, match="sudo authentication failed"):
        host_apply_logic.apply(host="h1", dry_run=False)


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
