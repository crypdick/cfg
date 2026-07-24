from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.fs import iter_files
from cfg.core.root import find_cfg_root, require_cfg_root

if TYPE_CHECKING:
    from pathlib import Path


def _touch(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_iter_files_edge_cases(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert iter_files(missing) == []

    f = tmp_path / "a.txt"
    _touch(f, "x")
    assert iter_files(f) == [f]

    d = tmp_path / "d"
    d.mkdir()
    (d / ".gitkeep").write_text("", encoding="utf-8")
    assert iter_files(d / ".gitkeep") == []
    _touch(d / "b.txt", "b")
    (d / "sub").mkdir()
    _touch(d / "sub" / "a.txt", "a")
    files = iter_files(d)
    assert [p.relative_to(d).as_posix() for p in files] == ["b.txt", "sub/a.txt"]

    # Non-file, non-dir (e.g. FIFO) should return [].
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert iter_files(fifo) == []


def test_find_cfg_root_resolution_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "cfgroot"
    root.mkdir()
    (root / ".cfg-root").write_text("", encoding="utf-8")

    # 1) env var
    monkeypatch.setenv("CFG_ROOT", str(root))
    assert find_cfg_root(start=tmp_path) == root.resolve()

    # 2) XDG hint file
    monkeypatch.delenv("CFG_ROOT", raising=False)
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    hint = xdg / "cfg" / "root"
    _touch(hint, str(root))
    assert find_cfg_root(start=tmp_path / "other") == root.resolve()

    # 3) upward search
    # Point XDG at empty temp dir so real ~/.config/cfg/root doesn't interfere.
    hint.unlink()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty_xdg"))
    start = root / "sub" / "dir"
    start.mkdir(parents=True)
    assert find_cfg_root(start=start) == root.resolve()

    # 4) default ~/.cfg personalization repository
    home = tmp_path / "home"
    default_root = home / ".cfg"
    default_root.mkdir(parents=True)
    (default_root / ".cfg-root").write_text("", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    assert find_cfg_root(start=tmp_path / "outside") == default_root.resolve()


def test_require_cfg_root_raises_with_hint_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.delenv("CFG_ROOT", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("HOME", str(tmp_path / "empty_home"))

    with pytest.raises(CfgError) as e:
        require_cfg_root(start=tmp_path)
    msg = str(e.value)
    assert "Could not locate cfg root" in msg
    assert str(xdg / "cfg" / "root") in msg
    assert "~/.cfg" in msg
