from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import suppress
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.ids import FeatureName
from cfg.core.owners import FeatureOwner, owner_id_to_dir
from cfg.core.scope import Scope
from cfg.core.special_files import storage_rel_from_logical_rel


def resolve_repo_link_dest(
    *,
    cfg_root: Path,
    rel_path: Path,
    feature: FeatureName,
) -> Path:
    """
    Compute the canonical owner overlay destination for linking a repo file.
    """
    rel_path = Path(rel_path)
    owner_id = FeatureOwner(scope=Scope.REPO, name=feature).id
    owner_dir = owner_id_to_dir(cfg_root, owner_id)
    return (owner_dir / "overlay" / storage_rel_from_logical_rel(rel_path)).resolve()


def link_repo_file(
    *,
    cfg_root: Path,
    repo_root: Path,
    rel_path: Path,
    feature: FeatureName,
) -> Path:
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

    temporary_dest: Path | None = None
    temporary_link: Path | None = None
    published_dest = False
    linked = False
    try:
        with tempfile.NamedTemporaryFile(
            dir=dest.parent,
            prefix=f".{dest.name}.",
            delete=False,
        ) as temporary:
            temporary_dest = Path(temporary.name)
        shutil.copy2(src_in_repo, temporary_dest)
        try:
            os.link(temporary_dest, dest)
            published_dest = True
        except FileExistsError as e:
            raise CfgError(f"Overlay file already exists: {dest}") from e

        with tempfile.NamedTemporaryFile(
            dir=raw.parent,
            prefix=f".{raw.name}.",
            delete=False,
        ) as temporary:
            temporary_link = Path(temporary.name)
        temporary_link.unlink()
        temporary_link.symlink_to(dest)
        temporary_link.replace(raw)
        linked = True
    finally:
        for temporary_path in (temporary_dest, temporary_link):
            if temporary_path is None:
                continue
            with suppress(FileNotFoundError):
                temporary_path.unlink()
        if published_dest and not linked:
            with suppress(FileNotFoundError):
                dest.unlink()
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

    # Ensure parent exists for the final destination.
    raw.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=raw.parent,
            prefix=f".{raw.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        shutil.copy2(target, temporary_path)
        temporary_path.replace(raw)
    finally:
        if temporary_path is not None:
            with suppress(FileNotFoundError):
                temporary_path.unlink()
    return target
