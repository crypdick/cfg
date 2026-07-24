from __future__ import annotations

from pathlib import Path

from cfg.core.cli_logic_utils import normalize_feature_name
from cfg.core.context import CfgContext
from cfg.core.errors import CfgError
from cfg.core.feature_validation import require_feature_exists_in_manifest
from cfg.core.scope import Scope
from cfg.repo.git import repo_root
from cfg.repo.overlay import link_repo_file, resolve_repo_link_dest, unlink_repo_file


def link(*, path: Path, feature: str, dry_run: bool = False) -> Path:
    """Business logic for `cfg repo link`."""
    ctx = CfgContext.load()
    rr = repo_root()
    feature_name = normalize_feature_name(feature, Scope.REPO)
    require_feature_exists_in_manifest(ctx, feature_name, Scope.REPO)
    if dry_run:
        # Plan mode: validate like the real operation, but do not mutate.
        raw = rr / Path(path)
        if not raw.exists():
            raise CfgError(f"File not found in repo: {path}")
        if raw.is_symlink():
            raise CfgError(f"Refusing to link a symlink: {path}")

        src_in_repo = raw.resolve()
        try:
            src_in_repo.relative_to(rr.resolve())
        except ValueError as e:
            raise CfgError(f"Refusing to link outside repo root: {path}") from e

        if src_in_repo.is_dir():
            raise CfgError(f"Cannot link a directory yet: {path}")

        dest = resolve_repo_link_dest(
            cfg_root=ctx.root,
            rel_path=Path(path),
            feature=feature_name,
        )
        if dest.exists():
            raise CfgError(f"Overlay file already exists: {dest}")
        return dest
    return link_repo_file(
        cfg_root=ctx.root,
        repo_root=rr,
        rel_path=path,
        feature=feature_name,
    )


def unlink(*, path: Path, dry_run: bool = False) -> Path:
    """Business logic for `cfg repo unlink`."""
    _ctx = CfgContext.load()
    rr = repo_root()
    return unlink_repo_file(repo_root=rr, rel_path=path, dry_run=dry_run)
