from __future__ import annotations

import subprocess
import tomllib
from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:owner/repo.git"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )


def test_repo_init_writes_repo_inventory_without_settings_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = tmp_path / "cfg-root"
    _write(cfg_root / ".cfg-root", "")

    _write(
        cfg_root / "features" / "repo" / "base" / "feature.toml",
        "schema_version = 1\nrequires = []\nconflicts = []\ngenerated = []\n",
    )
    _write(
        cfg_root / "features" / "repo" / "uv" / "feature.toml",
        "schema_version = 1\nrequires = []\nconflicts = []\ngenerated = []\n",
    )

    # Host hint required by cfg context.
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _write(tmp_path / "xdg" / "cfg" / "host", "h1\n")

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.init as repo_init_logic
    import main

    # Keep the test focused on inventory writing; attachment is tested elsewhere.
    monkeypatch.setattr(repo_init_logic, "attach_repo", lambda **_kwargs: None)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "init", "--host", "h1", "--feature", "uv"])
    assert res.exit_code == 0, (res.output, res.exception)

    out_path = cfg_root / "repos" / "owner" / "repo" / "cfg.toml"
    assert out_path.is_file()

    data = tomllib.loads(out_path.read_text(encoding="utf-8"))
    assert data["id"] == "owner/repo"
    assert "settings" not in data  # repo settings stay at the top level

    # Idempotency: running init again should not crash.
    res2 = runner.invoke(main.app, ["repo", "init", "--host", "h1"])
    assert res2.exit_code == 0, (res2.output, res2.exception)
