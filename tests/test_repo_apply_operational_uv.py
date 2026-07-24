from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

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


def _setup_min_cfg_root(tmp_path: Path) -> Path:
    cfg_root = tmp_path / "cfg-root"
    _write(cfg_root / ".cfg-root", "")

    # Minimal owner manifests to exercise repo->host cross-scope deps:
    # repo/feature/uv -> host/feature/uv -> host/feature/base
    _write(
        cfg_root / "features" / "repo" / "python" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "host" / "base" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "host" / "uv" / "feature.toml",
        """
schema_version = 1
requires = ["base"]
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "repo" / "base" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "repo" / "uv" / "feature.toml",
        """
schema_version = 1
requires = ["python"]
host_requires = ["uv"]
conflicts = []
generated = []
""".lstrip(),
    )

    # Minimal inventory: one host, one repo.
    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        """
name = "h1"
features = []
""".lstrip(),
    )
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = ["uv"]
""".lstrip(),
    )

    return cfg_root


def _setup_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    return repo_root


def test_repo_apply_missing_uv_errors_with_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_min_cfg_root(tmp_path)
    repo_root = _setup_repo(tmp_path)

    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _write(tmp_path / "xdg" / "cfg" / "host", "h1\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.apply as repo_apply_logic
    import main

    monkeypatch.setattr(repo_apply_logic, "_uv_exists", lambda: False)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "apply", "--allow-dirty"])

    msg = (res.output or "") + ("\n" + str(res.exception) if res.exception else "")
    assert res.exit_code != 0
    assert "Missing host prerequisite" in msg
    assert "uv" in msg
    assert "cfg host apply" in msg
    assert "--ensure-host" in msg


def test_repo_apply_ensure_host_triggers_host_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_min_cfg_root(tmp_path)
    repo_root = _setup_repo(tmp_path)

    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _write(tmp_path / "xdg" / "cfg" / "host", "h1\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.apply as repo_apply_logic
    import main

    state = {"uv": False}
    calls: dict[str, list[Any]] = {"host": [], "apply": []}

    def fake_uv_exists() -> bool:
        return bool(state["uv"])

    def fake_run_host_pyinfra(**kwargs: Any) -> None:
        calls["host"].append(dict(kwargs))
        state["uv"] = True

    def fake_apply_repo_plan(plan: Any) -> int:
        calls["apply"].append(plan)
        return 0

    monkeypatch.setattr(repo_apply_logic, "_uv_exists", fake_uv_exists)
    monkeypatch.setattr(repo_apply_logic, "run_host_pyinfra", fake_run_host_pyinfra)
    monkeypatch.setattr(repo_apply_logic, "apply_repo_plan", fake_apply_repo_plan)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "apply", "--ensure-host", "--allow-dirty"])
    assert res.exit_code == 0, (res.output, res.exception)

    assert len(calls["host"]) == 1
    assert "CFG_EXTRA_HOST_OWNER_IDS" in (calls["host"][0].get("extra_env") or {})
    assert len(calls["apply"]) == 1
