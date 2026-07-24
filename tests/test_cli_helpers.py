from __future__ import annotations

import os
from pathlib import Path

import pytest
import typer

from cfg.core.cli_helpers import (
    copy_to_managed,
    resolve_existing_user_path,
    resolve_relative_user_path,
    safe_remove_within_root,
)
from cfg.core.errors import CfgError


def _write(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_resolve_relative_user_path_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(typer.BadParameter, match="cannot be empty"):
        resolve_relative_user_path(base_dir=tmp_path, user_path="   ")


def test_resolve_relative_user_path_relative_normalizes_and_rejects_dotdot(tmp_path: Path) -> None:
    assert resolve_relative_user_path(base_dir=tmp_path, user_path="a/b") == Path("a/b")
    with pytest.raises(ValueError, match="Unsafe relative path"):
        resolve_relative_user_path(base_dir=tmp_path, user_path="../x")


def test_resolve_relative_user_path_absolute_must_be_within_base(tmp_path: Path) -> None:
    inside = tmp_path / "a" / "b"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text("x", encoding="utf-8")

    rel = resolve_relative_user_path(base_dir=tmp_path, user_path=str(inside))
    assert rel == Path("a/b")

    with pytest.raises(typer.BadParameter, match="must be inside base directory"):
        resolve_relative_user_path(base_dir=tmp_path, user_path="/")


def test_resolve_relative_user_path_expand_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    p = tmp_path / "homefile"
    p.write_text("x", encoding="utf-8")

    # "~" expands into an absolute path, which is then validated to be within base_dir.
    rel = resolve_relative_user_path(base_dir=tmp_path, user_path="~/homefile", expand_user=True)
    assert rel == Path("homefile")


def test_copy_to_managed_file_and_gitignore_mapping(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"

    _write(src_root / ".gitignore", "ignored\n")
    n = copy_to_managed(src_root=src_root, dest_root=dest_root, rel=Path(".gitignore"))
    assert n == 1

    # Stored on disk as `__,gitignore` so it won't affect this repo's behavior.
    assert (dest_root / "__,gitignore").is_file()
    assert not (dest_root / ".gitignore").exists()


def test_copy_to_managed_directory_dry_run_counts_files(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"

    _write(src_root / "d" / "a.txt", "a")
    _write(src_root / "d" / "b.txt", "b")
    n = copy_to_managed(src_root=src_root, dest_root=dest_root, rel=Path("d"), dry_run=True)
    assert n == 2
    assert not dest_root.exists()


def test_copy_to_managed_refuses_overwrite_without_force(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    _write(src_root / "a.txt", "src")
    _write(dest_root / "a.txt", "dest")

    with pytest.raises(CfgError, match="Already managed"):
        copy_to_managed(src_root=src_root, dest_root=dest_root, rel=Path("a.txt"), force=False)


def test_copy_to_managed_refuses_git_internal_paths(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    _write(src_root / ".git" / "config", "x")

    with pytest.raises(CfgError, match="Refusing to manage special git path component"):
        copy_to_managed(src_root=src_root, dest_root=dest_root, rel=Path(".git"))


def test_resolve_existing_user_path_validates_exists_and_refuses_symlink(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()

    _write(base_dir / "f.txt", "x")
    rel, src = resolve_existing_user_path(
        base_dir=base_dir,
        user_path="f.txt",
        location="base",
        action="copy",
    )
    assert rel == Path("f.txt")
    assert src == (base_dir / "f.txt").resolve()

    with pytest.raises(typer.BadParameter, match="Path not found"):
        resolve_existing_user_path(
            base_dir=base_dir,
            user_path="missing.txt",
            location="base",
            action="copy",
        )

    link = base_dir / "link.txt"
    os.symlink(base_dir / "f.txt", link)
    with pytest.raises(typer.BadParameter, match="Refusing to copy a symlink"):
        resolve_existing_user_path(
            base_dir=base_dir,
            user_path="link.txt",
            location="base",
            action="copy",
        )


def test_safe_remove_within_root_outside_root_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(CfgError, match="Refusing to remove outside"):
        safe_remove_within_root(root=root, rel=Path("../oops"), dry_run=False, scope="root")


def test_safe_remove_within_root_dry_run_and_delete(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    _write(root / "f.txt", "x")
    target, existed = safe_remove_within_root(root=root, rel=Path("f.txt"), dry_run=True, scope="root")
    assert existed is True
    assert target == (root / "f.txt").resolve()
    assert (root / "f.txt").is_file()

    target, existed = safe_remove_within_root(root=root, rel=Path("f.txt"), dry_run=False, scope="root")
    assert existed is True
    assert not (root / "f.txt").exists()

    (root / "d").mkdir()
    _write(root / "d" / "a.txt", "a")
    target, existed = safe_remove_within_root(root=root, rel=Path("d"), dry_run=False, scope="root")
    assert existed is True
    assert target.name == "d"
    assert not (root / "d").exists()
