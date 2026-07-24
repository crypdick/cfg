from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

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


def _setup_cfg_root(tmp_path: Path) -> Path:
    cfg_root = tmp_path / "cfg-root"
    _write(cfg_root / ".cfg-root", "")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/desktop")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/base")
    return cfg_root


def _setup_xdg(tmp_path: Path, *, cfg_root: Path, host_hint: str | None = None) -> Path:
    xdg = tmp_path / "xdg"
    _write(xdg / "cfg" / "root", str(cfg_root) + "\n")
    if host_hint is not None:
        _write(xdg / "cfg" / "host", host_hint + "\n")
    return xdg


def _init_git_repo(repo_root: Path, *, repo_id: str) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"git@github.com:{repo_id}.git"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )


def test_repo_init_registers_repo_per_host_without_touching_repo_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Scenario:
    - repo init on host A registers repo + registers repo path on host A
    - repo init on host B (same repo id, different path) must NOT change repo registration,
      only add registration for host B
    """
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))

    import main

    runner = CliRunner()

    # Host A.
    xdg_a = _setup_xdg(tmp_path / "host-a", cfg_root=cfg_root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_a))
    repo_a = tmp_path / "repo-a"
    _init_git_repo(repo_a, repo_id="owner/repo")
    monkeypatch.chdir(repo_a)

    res_ha = runner.invoke(main.app, ["host", "init", "host-a"])
    assert res_ha.exit_code == 0, (res_ha.output, res_ha.exception)

    res_ra = runner.invoke(main.app, ["repo", "init"])
    assert res_ra.exit_code == 0, (res_ra.output, res_ra.exception)

    repo_inv_path = cfg_root / "repos" / "owner" / "repo" / "cfg.toml"
    host_a_inv_path = cfg_root / "hosts" / "host-a" / "cfg.toml"
    assert repo_inv_path.is_file()
    assert host_a_inv_path.is_file()

    repo_inv_before = repo_inv_path.read_text(encoding="utf-8")
    host_a_before = host_a_inv_path.read_text(encoding="utf-8")

    # Host B.
    xdg_b = _setup_xdg(tmp_path / "host-b", cfg_root=cfg_root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_b))
    repo_b = tmp_path / "repo-b"
    _init_git_repo(repo_b, repo_id="owner/repo")
    monkeypatch.chdir(repo_b)

    res_hb = runner.invoke(main.app, ["host", "init", "host-b"])
    assert res_hb.exit_code == 0, (res_hb.output, res_hb.exception)

    res_rb = runner.invoke(main.app, ["repo", "init"])
    assert res_rb.exit_code == 0, (res_rb.output, res_rb.exception)

    host_b_inv_path = cfg_root / "hosts" / "host-b" / "cfg.toml"
    assert host_b_inv_path.is_file()

    # Repo registration must not change.
    assert repo_inv_path.read_text(encoding="utf-8") == repo_inv_before

    # Host A registration must not change.
    assert host_a_inv_path.read_text(encoding="utf-8") == host_a_before

    # Host B registration must include this repo at repo_b path.
    host_b_text = host_b_inv_path.read_text(encoding="utf-8")
    assert 'name = "host-b"' in host_b_text
    assert '"owner/repo" = ' in host_b_text
    assert str(repo_b.resolve()) in host_b_text


def test_repo_init_is_idempotent_on_same_repo_same_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Scenario:
    - running repo init multiple times in the same repo on the same host should be effectively a no-op:
      inventory + attachment artifacts remain unchanged.
    """
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))

    xdg = _setup_xdg(tmp_path / "host", cfg_root=cfg_root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    repo = tmp_path / "repo"
    _init_git_repo(repo, repo_id="owner/repo")
    monkeypatch.chdir(repo)

    import main

    runner = CliRunner()
    assert runner.invoke(main.app, ["host", "init", "h1"]).exit_code == 0

    res1 = runner.invoke(main.app, ["repo", "init"])
    assert res1.exit_code == 0, (res1.output, res1.exception)

    repo_inv_path = cfg_root / "repos" / "owner" / "repo" / "cfg.toml"
    host_inv_path = cfg_root / "hosts" / "h1" / "cfg.toml"
    exclude_path = repo / ".git" / "info" / "exclude"
    hook_path = repo / ".git" / "hooks" / "pre-commit"
    state_path = repo / ".cfg" / "state.json"

    snapshot = {
        "repo_inv": repo_inv_path.read_text(encoding="utf-8"),
        "host_inv": host_inv_path.read_text(encoding="utf-8"),
        "exclude": exclude_path.read_text(encoding="utf-8") if exclude_path.is_file() else "",
        "hook": hook_path.read_text(encoding="utf-8") if hook_path.is_file() else "",
        "state": state_path.read_text(encoding="utf-8") if state_path.is_file() else "",
    }

    res2 = runner.invoke(main.app, ["repo", "init"])
    assert res2.exit_code == 0, (res2.output, res2.exception)

    assert repo_inv_path.read_text(encoding="utf-8") == snapshot["repo_inv"]
    assert host_inv_path.read_text(encoding="utf-8") == snapshot["host_inv"]
    assert (exclude_path.read_text(encoding="utf-8") if exclude_path.is_file() else "") == snapshot["exclude"]
    assert (hook_path.read_text(encoding="utf-8") if hook_path.is_file() else "") == snapshot["hook"]
    assert (state_path.read_text(encoding="utf-8") if state_path.is_file() else "") == snapshot["state"]


def test_host_init_is_idempotent_on_existing_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Scenario:
    - running host init multiple times for the same host should be effectively a no-op:
      host inventory + local hint remain unchanged.
    """
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))

    xdg = _setup_xdg(tmp_path / "host", cfg_root=cfg_root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    import main

    runner = CliRunner()
    res1 = runner.invoke(main.app, ["host", "init", "h1", "--feature", "desktop"])
    assert res1.exit_code == 0, (res1.output, res1.exception)

    host_inv_path = cfg_root / "hosts" / "h1" / "cfg.toml"
    hint_path = xdg / "cfg" / "host"
    assert host_inv_path.is_file()
    assert hint_path.is_file()

    inv_before = host_inv_path.read_text(encoding="utf-8")
    hint_before = hint_path.read_text(encoding="utf-8")

    res2 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res2.exit_code == 0, (res2.output, res2.exception)

    assert host_inv_path.read_text(encoding="utf-8") == inv_before
    assert hint_path.read_text(encoding="utf-8") == hint_before
