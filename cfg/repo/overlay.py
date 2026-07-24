from __future__ import annotations

import shutil
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.owners import owner_id_to_dir
from cfg.core.special_files import storage_rel_from_logical_rel


def resolve_repo_link_dest(*, cfg_root: Path, rel_path: Path, feature: str) -> Path:
    """
    Compute the canonical owner overlay destination for linking a repo file.
    """
    rel_path = Path(rel_path)
    owner_id = f"repo/feature/{feature}"
    owner_dir = owner_id_to_dir(cfg_root, owner_id)
    return (owner_dir / "overlay" / storage_rel_from_logical_rel(rel_path)).resolve()


def link_repo_file(*, cfg_root: Path, repo_root: Path, rel_path: Path, feature: str) -> Path:
    """
    Link a repo file into an owner payload overlay:
    - copies repo_root/rel_path -> features/repo/<feature>/overlay/rel_path
    - turns repo_root/rel_path into a symlink to the canonical file
    """
    rel_path = Path(rel_path)
    raw = repo_root / rel_path
    if not raw.exists():
        raise CfgError(f"File not found in repo: {rel_path}")
    if raw.is_symlink():
        raise CfgError(f"Refusing to link a symlink: {rel_path}")

    src_in_repo = raw.resolve()
    # Safety: refuse symlink/FS escapes outside the repo root.
    try:
        src_in_repo.relative_to(repo_root.resolve())
    except ValueError as e:
        raise CfgError(f"Refusing to promote outside repo root: {rel_path}") from e

    if src_in_repo.is_dir():
        raise CfgError(f"Cannot link a directory yet: {rel_path}")

    dest = resolve_repo_link_dest(cfg_root=cfg_root, rel_path=rel_path, feature=feature)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise CfgError(f"Overlay file already exists: {dest}")

    shutil.copy2(src_in_repo, dest)
    (repo_root / rel_path).unlink()
    (repo_root / rel_path).symlink_to(dest)
    return dest


def unlink_repo_file(*, repo_root: Path, rel_path: Path, dry_run: bool = False) -> Path:
    """
    Unlink a repo file:
    - requires repo_root/rel_path to be a symlink
    - copies the symlink target into a regular file at repo_root/rel_path

    Safety:
    - refuses to unlink if the symlink target does not exist or is a directory
    - does not delete the target payload file (keeps the overlay)
    """
    rel_path = Path(rel_path)
    raw = repo_root / rel_path
    if not raw.exists():
        raise CfgError(f"File not found in repo: {rel_path}")
    if not raw.is_symlink():
        raise CfgError(f"Refusing to unlink a non-symlink: {rel_path}")

    target = raw.resolve()
    if not target.exists():
        raise CfgError(f"Broken symlink target for {rel_path}: {target}")
    if target.is_dir():
        raise CfgError(f"Refusing to unlink a symlink to a directory: {rel_path}")

    if dry_run:
        return target

    tmp = repo_root / (storage_rel_from_logical_rel(rel_path).as_posix() + ".cfg-unlink-tmp")
    # Ensure parent exists for the final destination.
    raw.parent.mkdir(parents=True, exist_ok=True)

    # Install a regular file atomically when the filesystem permits it.
    # Note: `tmp` path lives under repo_root, so this can't escape the repo.
    tmp.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, tmp)
    raw.unlink()
    tmp.replace(raw)
    return target
