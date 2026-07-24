from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

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
    _write(
        cfg_root / "features" / "repo" / "python" / "feature.toml",
        "schema_version = 1\n",
    )

    xdg = tmp_path / "xdg"
    _write(xdg / "cfg" / "root", str(cfg_root) + "\n")
    _write(xdg / "cfg" / "host", host_hint + "\n")
    return cfg_root


def test_repo_link_rejects_unknown_feature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / "a.txt", "hello\n")
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import linking

    with pytest.raises(CfgError, match="Feature not found"):
        linking.link(path=Path("a.txt"), feature="missing", dry_run=True)


def test_repo_link_dry_run_refuses_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(tmp_path / "cfg-root"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import linking

    with pytest.raises(CfgError, match="File not found in repo"):
        linking.link(path=Path("missing.txt"), feature="python", dry_run=True)


def test_repo_link_dry_run_refuses_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(tmp_path / "cfg-root"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / "a.txt", "hello\n")
    (repo_root / "link.txt").symlink_to("a.txt")
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import linking

    with pytest.raises(CfgError, match="Refusing to link a symlink"):
        linking.link(path=Path("link.txt"), feature="python", dry_run=True)


def test_repo_link_dry_run_refuses_outside_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(tmp_path / "cfg-root"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)

    # Create a file outside the repo root that is reachable via a relative path.
    _write(tmp_path / "outside.txt", "nope\n")
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import linking

    with pytest.raises(CfgError, match="Refusing to link outside repo root"):
        linking.link(path=Path("../outside.txt"), feature="python", dry_run=True)


def test_repo_link_dry_run_refuses_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(tmp_path / "cfg-root"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    (repo_root / "dir").mkdir()
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import linking

    with pytest.raises(CfgError, match="Cannot link a directory yet"):
        linking.link(path=Path("dir"), feature="python", dry_run=True)


def test_repo_link_dry_run_refuses_when_overlay_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / "a.txt", "hello\n")
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import linking

    dest = tmp_path / "already-exists.txt"
    _write(dest, "x\n")
    monkeypatch.setattr(linking, "resolve_repo_link_dest", lambda **_kw: dest)

    with pytest.raises(CfgError, match="Overlay file already exists"):
        linking.link(path=Path("a.txt"), feature="python", dry_run=True)


def test_repo_link_dry_run_returns_dest_when_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / "a.txt", "hello\n")
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import linking

    dest = tmp_path / "dest.txt"
    monkeypatch.setattr(linking, "resolve_repo_link_dest", lambda **_kw: dest)
    out = linking.link(path=Path("a.txt"), feature="python", dry_run=True)
    assert out == dest


def test_repo_unlink_delegates_and_passes_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(tmp_path / "cfg-root"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import linking

    called: dict[str, Any] = {}

    def fake_unlink_repo_file(*, repo_root: Path, rel_path: Path, dry_run: bool) -> Path:
        called.update({"repo_root": repo_root, "rel_path": rel_path, "dry_run": dry_run})
        return Path("/tmp/unlinked")

    monkeypatch.setattr(linking, "unlink_repo_file", fake_unlink_repo_file)

    out = linking.unlink(path=Path("x.txt"), dry_run=True)
    assert out == Path("/tmp/unlinked")
    assert called.get("dry_run") is True
