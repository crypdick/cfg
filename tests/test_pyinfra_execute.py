from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cfg.core.errors import CfgError
from cfg.pyinfra import execute as ex

if TYPE_CHECKING:
    from pathlib import Path


def test_pyinfra_bootstrap_is_valid_python() -> None:
    compile(ex.PYINFRA_BOOTSTRAP, "<pyinfra-bootstrap>", "exec")


def test_run_pyinfra_cli_builds_command_and_sets_yes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    class _P:
        def __init__(self, code: int):
            self.returncode = code

    monkeypatch.setattr(ex.sys.stdin, "isatty", lambda: False)

    def fake_run(cmd: Any, cwd: Any = None, env: Any = None, timeout: Any = None, **_kw: Any) -> _P:
        calls.append({"cmd": list(cmd), "cwd": cwd, "env": dict(env or {}), "timeout": timeout})
        return _P(0)

    monkeypatch.setattr(ex.subprocess, "run", fake_run)

    ex.run_pyinfra_cli(
        cwd=tmp_path,
        inventory_path=tmp_path / "inventory.py",
        operations=["deploy.py"],
        limit=["h1", "@local"],
        extra_env={"X": "1"},
    )

    assert calls, "expected subprocess.run call"
    cmd = calls[-1]["cmd"]
    assert cmd[0:2] == [ex.sys.executable, "-c"]
    assert "--yes" in cmd
    assert cmd.count("--limit") == 2
    assert str(tmp_path / "inventory.py") in cmd
    assert "deploy.py" in cmd
    assert calls[-1]["cwd"] == str(tmp_path)
    assert calls[-1]["env"]["X"] == "1"


def test_run_pyinfra_cli_dry_run_adds_dry_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    class _P:
        def __init__(self, code: int):
            self.returncode = code

    monkeypatch.setattr(ex.sys.stdin, "isatty", lambda: True)

    def fake_run(cmd: Any, cwd: Any = None, env: Any = None, timeout: Any = None, **_kw: Any) -> _P:
        calls.append({"cmd": list(cmd), "cwd": cwd, "env": dict(env or {}), "timeout": timeout})
        return _P(0)

    monkeypatch.setattr(ex.subprocess, "run", fake_run)

    ex.run_pyinfra_cli(
        cwd=tmp_path,
        inventory_path=tmp_path / "inventory.py",
        operations=["deploy.py"],
        dry_run=True,
    )

    assert calls, "expected subprocess.run call"
    assert "--dry" in calls[-1]["cmd"]


def test_run_pyinfra_cli_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ex.sys.stdin, "isatty", lambda: True)

    class _P:
        def __init__(self, code: int):
            self.returncode = code

    monkeypatch.setattr(ex.subprocess, "run", lambda *_a, **_kw: _P(7))
    with pytest.raises(CfgError) as e:
        ex.run_pyinfra_cli(
            cwd=tmp_path,
            inventory_path=tmp_path / "inventory.py",
            operations=["deploy.py"],
        )
    assert "exit code 7" in str(e.value)


def test_run_pyinfra_delegates_to_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, Any] = {}
    monkeypatch.setattr(ex, "run_pyinfra_cli", lambda **kwargs: called.update(kwargs))

    inventory_path = tmp_path / "inventory.py"
    ex.run_pyinfra(
        cwd=tmp_path,
        inventory_path=inventory_path,
        operations=["deploy.py"],
        limit=["all"],
        extra_env={"X": "1"},
        dry_run=True,
        quiet=True,
    )

    assert called == {
        "cwd": tmp_path,
        "inventory_path": inventory_path,
        "operations": ["deploy.py"],
        "limit": ["all"],
        "extra_env": {"X": "1"},
        "dry_run": True,
        "quiet": True,
    }
