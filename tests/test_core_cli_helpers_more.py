from __future__ import annotations

import os
from pathlib import Path

import pytest
import typer

from cfg.core.cli_helpers import copy_to_managed, resolve_existing_user_path
from cfg.core.errors import CfgError


def test_copy_to_managed_dir_conflict_raises(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    (src_root / "d").mkdir(parents=True, exist_ok=True)
    (dest_root / "d").mkdir(parents=True, exist_ok=True)
    (src_root / "d" / "a.txt").write_text("a\n", encoding="utf-8")

    # Pre-create the destination to trigger the "Already managed" conflict.
    (dest_root / "d" / "a.txt").write_text("existing\n", encoding="utf-8")

    with pytest.raises(CfgError, match="Already managed"):
        copy_to_managed(src_root=src_root, dest_root=dest_root, rel=Path("d"))


def test_copy_to_managed_unsupported_path_type(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    fifo_rel = Path("fifo")
    os.mkfifo(src_root / fifo_rel)

    with pytest.raises(typer.BadParameter, match="Unsupported path type"):
        copy_to_managed(src_root=src_root, dest_root=dest_root, rel=fifo_rel)


def test_resolve_existing_user_path_rejects_symlink(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (tmp_path / "outside.txt").write_text("x\n", encoding="utf-8")
    (base / "link").symlink_to(tmp_path / "outside.txt")

    with pytest.raises(typer.BadParameter, match="Refusing to add a symlink"):
        resolve_existing_user_path(
            base_dir=base,
            user_path="link",
            location="home",
            action="add",
        )


def test_resolve_existing_user_path_rejects_symlink_escape_via_parent_dir(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.txt").write_text("x\n", encoding="utf-8")

    # Parent dir is a symlink to outside, but the file itself is not a symlink.
    (base / "sub").symlink_to(outside, target_is_directory=True)

    with pytest.raises(typer.BadParameter, match="inside base directory"):
        resolve_existing_user_path(
            base_dir=base,
            user_path="sub/x.txt",
            location="home",
            action="add",
        )
