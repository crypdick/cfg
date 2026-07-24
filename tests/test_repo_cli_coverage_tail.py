from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from cfg.core.errors import CfgError

if TYPE_CHECKING:
    import pytest


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_feature_manifest(*, cfg_root: Path, owner_id: str) -> None:
    parts = owner_id.split("/")
    assert len(parts) >= 3, owner_id
    assert parts[1] == "feature", owner_id
    scope = parts[0]
    rel = Path(*parts[2:])
    path = cfg_root / "features" / scope / rel / "feature.toml"
    _write(
        path,
        ("schema_version = 1\nrequires = []\nconflicts = []\ngenerated = []\n"),
    )


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:owner/repo.git"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )


def _setup_cfg_root(tmp_path: Path, *, host_hint: str = "h1") -> Path:
    cfg_root = tmp_path / "cfg-root"
    _write(cfg_root / ".cfg-root", "")

    xdg = tmp_path / "xdg"
    _write(xdg / "cfg" / "root", str(cfg_root) + "\n")
    _write(xdg / "cfg" / "host", host_hint + "\n")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/uv")
    return cfg_root


def test_uv_exists_true_and_false(monkeypatch: pytest.MonkeyPatch) -> None:
    import cfg.repo.logic.apply as repo_apply_logic

    # CfgError path -> False
    monkeypatch.setattr(
        repo_apply_logic, "run_cmd", lambda *_a, **_k: (_ for _ in ()).throw(CfgError("boom"))
    )
    assert repo_apply_logic._uv_exists() is False

    # Normal output -> True
    monkeypatch.setattr(repo_apply_logic, "run_cmd", lambda *_a, **_k: "uv 0.1.0\n")
    assert repo_apply_logic._uv_exists() is True


def test_repo_init_backfills_origin_url_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Create base repo inventory with missing origin_url.
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []

""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.init as repo_init_logic
    import main

    # Make origin_url return a value so init fills it.
    monkeypatch.setattr(repo_init_logic, "origin_url", lambda *_a, **_k: "https://github.com/owner/repo.git")
    # Avoid side-effecty attach.
    monkeypatch.setattr(repo_init_logic, "attach_repo", lambda **_kw: None)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "init", "--host", "h1"])
    assert res.exit_code == 0, (res.output, res.exception)

    data = tomllib.loads((cfg_root / "repos" / "owner" / "repo" / "cfg.toml").read_text(encoding="utf-8"))
    assert data["origin_url"] == "https://github.com/owner/repo.git"


def test_repo_apply_non_dry_run_prints_changed_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Minimal repo inventory just so require_registered_repo passes.
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []

""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.apply as repo_apply_logic
    import main

    monkeypatch.setattr(repo_apply_logic, "resolved_repo_owner_ids", lambda **_kw: [])
    monkeypatch.setattr(repo_apply_logic, "attach_repo", lambda **_kw: None)

    monkeypatch.setattr(repo_apply_logic, "run_cmd", lambda *_a, **_kw: "")

    from cfg.repo.plan import RepoApplyPlan

    plan = RepoApplyPlan(cfg_root=cfg_root, repo_root=repo_root, operations=())
    monkeypatch.setattr(repo_apply_logic, "build_repo_apply_plan", lambda **_kw: plan)
    monkeypatch.setattr(repo_apply_logic, "apply_repo_plan", lambda _plan: 1)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "apply"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "changed: 1 managed repo path(s)" in res.output
