"""Focused regressions for CLI and host behaviors that previously broke."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cfg.core.errors import CfgError


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


def _setup_cfg_root(tmp_path: Path, *, host_hint: str = "h1") -> Path:
    cfg_root = tmp_path / "cfg-root"
    _write(cfg_root / ".cfg-root", "")

    xdg = tmp_path / "xdg"
    _write(xdg / "cfg" / "root", str(cfg_root) + "\n")
    _write(xdg / "cfg" / "host", host_hint + "\n")
    return cfg_root


def _write_host_inventory(cfg_root: Path, host: str) -> None:
    _write(
        cfg_root / "hosts" / host / "cfg.toml",
        f'name = "{host}"\nfeatures = []\n',
    )


def test_safe_host_slug_rejects_empty_and_nested_names(tmp_path: Path) -> None:
    from cfg.host.fs import safe_host_slug

    with pytest.raises(CfgError):
        safe_host_slug("")
    with pytest.raises(CfgError):
        safe_host_slug("a/b")


def test_host_mirror_remove_reports_unmanaged_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    _write_host_inventory(cfg_root, "h1")

    # Keep home deterministic.
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    home.mkdir(parents=True, exist_ok=True)

    from cfg.host.logic import mirror

    out = mirror.remove_path(path="missing.txt", host="h1", dry_run=False)
    assert out == ["no change (not managed)."]


def test_host_sync_repos_reports_empty_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    _write_host_inventory(cfg_root, "h1")

    from cfg.host.logic import sync_repos as host_sync_repos

    out = host_sync_repos.sync_repos(
        host="h1",
        fetch_only=True,
        remote="origin",
        allow_dirty=False,
        submodules=False,
        dry_run=False,
    )
    assert out == ["(no repos configured for host)"]


def test_host_sync_repos_reports_updated_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        """
name = "h1"
features = []


[repos]
"a/b" = "/tmp/a"
""".lstrip(),
    )

    from cfg.host.logic import sync_repos as host_sync_repos

    class _Res:
        fetched = False
        updated = True
        message = "updated"
        path = Path("/tmp/a")

    monkeypatch.setattr(host_sync_repos, "sync_repo", lambda **_kw: _Res())

    lines = host_sync_repos.sync_repos(
        host="h1",
        fetch_only=False,
        remote="origin",
        allow_dirty=False,
        submodules=False,
        dry_run=False,
    )
    assert "summary:" in "\n".join(lines)


def test_host_debug_inventory_can_skip_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from cfg.host.logic import debug_inventory as host_debug

    monkeypatch.setattr(
        host_debug, "run_pyinfra_debug_inventory", lambda **_kw: (_ for _ in ()).throw(RuntimeError)
    )
    out = host_debug.debug_inventory(hosts=None, print_generated=False, run=False)
    assert out is None


def test_host_debug_inventory_runs_when_requested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from cfg.host.logic import debug_inventory as host_debug

    called: dict[str, Any] = {}
    monkeypatch.setattr(host_debug, "run_pyinfra_debug_inventory", lambda **kw: called.update(kw))

    out = host_debug.debug_inventory(hosts=None, print_generated=False, run=True)
    assert out is None
    assert "cfg_root" in called


def test_host_app_init_maps_value_error_to_cli_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.api as host_logic_api
    import main

    monkeypatch.setattr(host_logic_api, "init_host", lambda **_kw: (_ for _ in ()).throw(ValueError("bad")))

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "init", "h1"])
    assert res.exit_code != 0


def test_repo_link_and_unlink_dry_run_print_destinations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.api as repo_logic_api
    import main

    monkeypatch.setattr(repo_logic_api, "link", lambda **_kw: Path("/tmp/dest"))
    monkeypatch.setattr(repo_logic_api, "unlink", lambda **_kw: Path("/tmp/dest2"))

    runner = CliRunner()

    res1 = runner.invoke(main.app, ["repo", "link", "a.txt", "--feature", "python", "--dry-run"])
    assert res1.exit_code == 0
    assert res1.output.strip() == "/tmp/dest"

    res2 = runner.invoke(main.app, ["repo", "unlink", "a.txt", "--dry-run"])
    assert res2.exit_code == 0
    assert res2.output.strip() == "/tmp/dest2"
