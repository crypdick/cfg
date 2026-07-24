"""
Small filesystem helpers shared across modules.
"""

from __future__ import annotations

from pathlib import Path


def iter_files(root: Path) -> list[Path]:
    """
    Recursively list all regular files under root (stable order).
    Skips `.gitkeep`. If root is a file, returns [root].
    """
    if not root.exists():
        return []
    if root.is_file():
        return [] if root.name == ".gitkeep" else [root]
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.name == ".gitkeep":
            continue
        out.append(p)
    return out
