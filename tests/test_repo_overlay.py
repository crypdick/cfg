from __future__ import annotations

from pathlib import Path

import pytest

from cfg.core.errors import CfgError
from cfg.repo.overlay import link_repo_file, unlink_repo_file


def _write(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_link_repo_file_happy_path_creates_overlay_and_symlink(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfgroot"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    _write(repo_root / "a.txt", "hello\n")

    dest = link_repo_file(cfg_root=cfg_root, repo_root=repo_root, rel_path=Path("a.txt"), feature="demo")
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == "hello\n"

    p = repo_root / "a.txt"
    assert p.is_symlink()
    assert p.resolve() == dest.resolve()


def test_link_repo_file_refuses_missing_dir_or_symlink(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfgroot"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    with pytest.raises(CfgError, match="File not found"):
        link_repo_file(cfg_root=cfg_root, repo_root=repo_root, rel_path=Path("missing.txt"), feature="demo")

    (repo_root / "d").mkdir()
    with pytest.raises(CfgError, match="Cannot link a directory"):
        link_repo_file(cfg_root=cfg_root, repo_root=repo_root, rel_path=Path("d"), feature="demo")

    _write(repo_root / "t.txt", "x")
    (repo_root / "link.txt").symlink_to(repo_root / "t.txt")
    with pytest.raises(CfgError, match="Refusing to link a symlink"):
        link_repo_file(cfg_root=cfg_root, repo_root=repo_root, rel_path=Path("link.txt"), feature="demo")


def test_link_repo_file_refuses_if_overlay_dest_exists(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfgroot"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    _write(repo_root / ".gitignore", "a\n")
    # First promotion should work.
    link_repo_file(cfg_root=cfg_root, repo_root=repo_root, rel_path=Path(".gitignore"), feature="demo")

    # Second attempt should refuse because overlay file exists already.
    # After promotion, the repo path is a symlink. Replace it with a real file to
    # specifically exercise the "overlay already exists" guard.
    p = repo_root / ".gitignore"
    assert p.is_symlink()
    p.unlink()
    _write(p, "b\n")
    with pytest.raises(CfgError, match="Overlay file already exists"):
        link_repo_file(cfg_root=cfg_root, repo_root=repo_root, rel_path=Path(".gitignore"), feature="demo")


def test_unlink_repo_file_happy_path_replaces_symlink_with_real_file(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfgroot"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    _write(repo_root / "a.txt", "hello\n")
    dest = link_repo_file(cfg_root=cfg_root, repo_root=repo_root, rel_path=Path("a.txt"), feature="demo")
    assert (repo_root / "a.txt").is_symlink()

    pointed_to = unlink_repo_file(repo_root=repo_root, rel_path=Path("a.txt"))
    assert pointed_to.resolve() == dest.resolve()

    p = repo_root / "a.txt"
    assert p.is_file()
    assert not p.is_symlink()
    assert p.read_text(encoding="utf-8") == "hello\n"
    # Keep overlay payload (unlink should not delete it)
    assert dest.is_file()
