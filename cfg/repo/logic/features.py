from __future__ import annotations

from typing import Any

from cfg.core.cli_logic_utils import (
    format_features_list,
    normalize_feature_name,
)
from cfg.core.context import CfgContext
from cfg.core.errors import CfgError
from cfg.core.feature_validation import (
    require_feature_exists_in_manifest,
)
from cfg.core.models import RepoSettings
from cfg.core.scope import Scope
from cfg.repo.cli_common import require_ctx_repo_id
from cfg.repo.git import origin_url, repo_root


def features_list() -> list[str]:
    """Business logic for `cfg repo feature list` (returns lines to print)."""
    ctx = CfgContext.load()
    rid = require_ctx_repo_id(ctx)

    entry = ctx.store.get_repo(rid)
    if entry is None:
        return ["(repo not registered)"]
    return format_features_list(entry.features)


def features_add(*, feature: str, dry_run: bool = False) -> list[str]:
    """Business logic for `cfg repo feature add` (returns lines to print)."""
    ctx = CfgContext.load()
    rid = require_ctx_repo_id(ctx)

    rr = repo_root()
    url = origin_url(rr)

    f = normalize_feature_name(feature, Scope.REPO)

    # Validate feature exists in manifest (fail fast with helpful error).
    require_feature_exists_in_manifest(ctx, f, Scope.REPO)

    loaded = ctx.store.get_repo(rid)
    if loaded is None:
        # Repo not registered yet - create entry with this feature.
        path = ctx.store.get_repo_path(rid)
        if dry_run:
            return [f"would create: {path}"]
        settings = RepoSettings(id=rid, origin_url=url, features=[f])
        path2 = ctx.store.save_repo(settings)
        return [f"created: {path2}"]

    features = list(loaded.features)

    # Idempotent: if already enabled, succeed with message (don't error).
    if f in features:
        return [f"ok (already enabled): {f}"]

    update: dict[str, Any] = {"features": [*features, f]}
    if loaded.origin_url is None and url:
        update["origin_url"] = url
    updated = loaded.model_copy(update=update)
    path = ctx.store.get_repo_path(rid)
    if dry_run:
        return [f"would update: {path}"]
    path2 = ctx.store.save_repo(updated)
    return [f"updated: {path2}"]


def features_remove(*, feature: str, dry_run: bool = False) -> list[str]:
    """Business logic for `cfg repo feature remove` (returns lines to print)."""
    ctx = CfgContext.load()
    rid = require_ctx_repo_id(ctx)
    f = normalize_feature_name(feature, Scope.REPO)

    # Validate feature exists in manifest (catch typos early).
    require_feature_exists_in_manifest(ctx, f, Scope.REPO)

    loaded = ctx.store.get_repo(rid)
    if loaded is None:
        raise CfgError(f"Repo not registered: {rid}\n\nTo register this repo:\n  cfg repo init")

    features = list(loaded.features)

    # Idempotent: if not enabled, succeed with message (don't error).
    if f not in features:
        return [f"ok (not enabled): {f}"]

    updated = loaded.model_copy(update={"features": [t for t in features if t != f]})
    path = ctx.store.get_repo_path(rid)
    if dry_run:
        return [f"would update: {path}"]
    path2 = ctx.store.save_repo(updated)
    return [f"updated: {path2}"]
