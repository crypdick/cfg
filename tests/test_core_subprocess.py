from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from cfg.core.errors import CfgError
from cfg.core.subprocess import run_cmd

if TYPE_CHECKING:
    from pathlib import Path


def test_run_cmd_success_strip_and_nostrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["x"], returncode=0, stdout=" ok \n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_cmd(["echo", "x"], cwd=tmp_path) == "ok"
    assert run_cmd(["echo", "x"], cwd=None, strip=False) == " ok \n"


def test_run_cmd_failure_check_true_includes_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["x"], returncode=2, stdout="", stderr="bad\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(CfgError, match=r"Command failed \(2\): echo x"):
        run_cmd(["echo", "x"], check=True)


def test_run_cmd_failure_check_false_returns_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["x"], returncode=2, stdout="out\n", stderr="bad\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_cmd(["echo", "x"], check=False) == "out"


def test_run_cmd_raises_on_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        raise OSError("boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(CfgError, match="Failed to run command"):
        run_cmd(["echo", "x"])
