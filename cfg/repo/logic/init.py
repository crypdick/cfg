from __future__ import annotations

from pathlib import Path
from typing import Any

from cfg.core.cli_logic_utils import normalize_feature_name
from cfg.core.context import CfgContext
from cfg.core.models import RepoSettings
from cfg.core.scope import Scope
from cfg.host.fs import safe_host_slug
from cfg.repo.attach import attach_repo
from cfg.repo.cli_common import require_ctx_repo_id
from cfg.repo.git import origin_url, repo_root


def init_repo(*, host: str | None, features: list[str], dry_run: bool) -> list[str]:
    """Business logic for `cfg repo init` (returns lines to print)."""
    ctx = CfgContext.load()
    rr = repo_root()  # Need physical repo root for origin_url and resolving paths

    rid = require_ctx_repo_id(ctx)
    host_name = safe_host_slug(host) if host else ctx.host_name

    # Repo inventory entry.
    existing_repo = ctx.store.get_repo(rid)
    base_repo = (
        existing_repo
        if existing_repo is not None
        else RepoSettings(id=rid, origin_url=origin_url(rr), features=[])
    )

    merged_features = list(base_repo.features) + [
        normalize_feature_name(t, Scope.REPO) for t in (features or []) if t
    ]
    repo_update: dict[str, Any] = {"features": merged_features}

    url = origin_url(rr)
    if base_repo.origin_url is None and url:
        repo_update["origin_url"] = url

    repo_updated = base_repo.model_copy(update=repo_update)
    repo_out_path = ctx.store.get_repo_path(rid)

    # Host inventory entry.
    existing_host = ctx.store.get_host(host_name)
    base_host = existing_host if existing_host is not None else None
    if base_host is None:
        from cfg.core.models import HostSettings

        base_host = HostSettings(name=host_name)

    repos_map = dict(base_host.repos or {})
    repos_map[rid] = rr.resolve()
    host_updated = base_host.model_copy(update={"repos": repos_map})
    host_out_path = ctx.store.get_host_path(host_name)

    # Execute.
    lines: list[str] = [f"repo_id: {rid}"]
    if dry_run:
        lines.append(f"would write: {repo_out_path}")
        lines.append(f"would update: {host_out_path} (repos[{rid}] = {rr})")
        lines.append("would attach repo.")
        return lines

    existed_repo = repo_out_path.is_file()
    ctx.store.save_repo(repo_updated)
    lines.append(("updated: " if existed_repo else "created: ") + str(repo_out_path))

    existed_host = host_out_path.is_file()
    ctx.store.save_host(host_updated)
    lines.append(("updated: " if existed_host else "created: ") + str(host_out_path))

    attach_repo(repo_root=rr, cfg_root=ctx.root)
    lines.append("attached.")
    return lines


def edit_repo() -> Path:
    """Business logic for `cfg repo edit`."""
    ctx = CfgContext.load()
    rid = require_ctx_repo_id(ctx)
    return ctx.store.get_repo_path(rid)
