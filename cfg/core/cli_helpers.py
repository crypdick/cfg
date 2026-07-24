from __future__ import annotations

import shutil
from pathlib import Path

import typer

from cfg.core.errors import CfgError
from cfg.core.models import safe_relpath
from cfg.core.special_files import storage_rel_from_logical_rel


def resolve_relative_user_path(base_dir: Path, user_path: str, *, expand_user: bool = False) -> Path:
    """
    Normalize a user-provided path into a base-relative Path.

    - Relative paths are interpreted relative to base_dir.
    - Absolute paths must be inside base_dir.
    - `..` is forbidden (via safe_relpath).
    """
    raw = str(user_path).strip()
    if not raw:
        raise typer.BadParameter("Path cannot be empty")

    p = Path(raw)
    if expand_user:
        p = p.expanduser()

    if p.is_absolute():
        try:
            rel = p.resolve().relative_to(base_dir.resolve())
        except ValueError as e:
            raise typer.BadParameter(f"Path must be inside base directory: {base_dir}") from e
        return rel

    # validate no ".." and normalize
    return safe_relpath(raw)


def copy_to_managed(
    *,
    src_root: Path,
    dest_root: Path,
    rel: Path,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Copy a file or directory from src_root to dest_root (preserving rel path).
    Returns the number of files copied.

    Special handling:
    - Nested `.gitignore` files are stored as `__,gitignore` so they don't affect
      git behavior inside this cfg repo. Logical destination paths remain `.gitignore`.
    """
    src = (src_root / rel).resolve()

    if src.is_file():
        dest = dest_root / storage_rel_from_logical_rel(rel)
        if dest.exists() and not force:
            raise CfgError(f"Already managed. Use --force to overwrite.\n- path: {rel}\n- dest: {dest}")
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return 1

    if src.is_dir():
        files = [p for p in sorted(src.rglob("*")) if p.is_file()]
        for p in files:
            rel_file = p.relative_to(src_root)
            dest = dest_root / storage_rel_from_logical_rel(rel_file)
            if dest.exists() and not force:
                raise CfgError(
                    f"Already managed. Use --force to overwrite.\n- path: {rel_file}\n- dest: {dest}"
                )

        if not dry_run:
            for p in files:
                rel_file = p.relative_to(src_root)
                dest = dest_root / storage_rel_from_logical_rel(rel_file)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        return len(files)

    raise typer.BadParameter(f"Unsupported path type: {rel}")


def resolve_existing_user_path(
    *,
    base_dir: Path,
    user_path: str,
    location: str,
    action: str,
    expand_user: bool = False,
) -> tuple[Path, Path]:
    """
    Resolve a user-provided path (relative/absolute) into a safe base-relative relpath,
    and validate that it exists and is not a symlink.
    """
    rel = resolve_relative_user_path(base_dir=base_dir, user_path=user_path, expand_user=expand_user)
    raw = base_dir / rel
    if not raw.exists():
        raise typer.BadParameter(f"Path not found in {location}: {rel}")
    if raw.is_symlink():
        raise typer.BadParameter(f"Refusing to {action} a symlink: {rel}")
    src = raw.resolve()
    # Safety: even for relative paths, refuse symlink/FS escapes outside base_dir.
    try:
        src.relative_to(base_dir.resolve())
    except Exception as e:
        raise typer.BadParameter(f"Path must be inside base directory: {base_dir}") from e
    return rel, src


def safe_remove_within_root(*, root: Path, rel: Path, dry_run: bool, scope: str) -> tuple[Path, bool]:
    """
    Remove a file/dir under `root/rel` safely.

    - Rejects targets outside of root (after resolving).
    - Returns (target_path, existed).
    """
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except Exception as e:
        raise CfgError(f"Refusing to remove outside {scope}: {target}") from e

    if not target.exists():
        return target, False

    if dry_run:
        return target, True

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return target, True
