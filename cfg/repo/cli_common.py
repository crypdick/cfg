from __future__ import annotations

from pathlib import Path

from cfg.core.context import CfgContext
from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId, RepoId
from cfg.core.models import RepoSettings
from cfg.core.owners import RepoOwner, resolve_repo_owner_ids
from cfg.core.protocols import RepoCtxLike
from cfg.core.scope import Scope
from cfg.repo.git import repo_root


def require_ctx_repo_id(ctx: RepoCtxLike) -> RepoId:
    if ctx.repo_id:
        return ctx.repo_id
    raise CfgError(
        "Could not determine repo id.\n\n"
        "Fix one of:\n"
        "- set a git `origin` remote (remote.origin.url) pointing at the repo\n"
    )


def repo_owner_id(repo_id: RepoId) -> OwnerId:
    return RepoOwner(repo_id=repo_id).id


def repo_ctx() -> tuple[CfgContext, Path, RepoId]:
    ctx = CfgContext.load()
    rr = repo_root()
    rid = require_ctx_repo_id(ctx)
    return ctx, rr, rid


def require_registered_repo(
    ctx: RepoCtxLike,
    rid: RepoId,
    *,
    include_hint: bool = False,
) -> RepoSettings:
    cfg = ctx.store.get_repo(rid)
    if cfg:
        return cfg
    if include_hint:
        hint = ctx.store.get_repo_path(rid)
        raise CfgError(f"Repo not registered: {rid}\nExpected: {hint}")
    raise CfgError(f"Repo not registered: {rid}")


def repo_enabled_owner_ids(cfg: RepoSettings) -> list[OwnerId]:
    """
    Enabled owner ids for a repo, derived from inventory.

    Semantics (2026-01):
    - repo-specific owner is always enabled: `repo/<owner>/<repo>`
    - repo settings store short feature names
    """
    return [
        repo_owner_id(cfg.id),
        Scope.REPO.base_feature_id,
        *(Scope.REPO.feature_id(feature) for feature in cfg.features),
    ]


def resolved_repo_owner_ids(*, cfg_root: Path, cfg: RepoSettings) -> list[OwnerId]:
    """
    Resolve repo owners with repo-scoped dependencies only.
    """
    return resolve_repo_owner_ids(cfg_root=cfg_root, enabled_repo_owner_ids=repo_enabled_owner_ids(cfg))
