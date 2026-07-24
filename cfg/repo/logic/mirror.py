from __future__ import annotations

from cfg.core.cli_helpers import (
    copy_to_managed,
    resolve_existing_user_path,
    resolve_relative_user_path,
    safe_remove_within_root,
)
from cfg.core.cli_logic_utils import NO_CHANGE_NOT_MANAGED
from cfg.core.owners import get_mirror_root
from cfg.repo.cli_common import repo_ctx, repo_owner_id, require_registered_repo


def add_path(*, path: str, force: bool, dry_run: bool) -> list[str]:
    """Business logic for `cfg repo mirror` (returns lines to print)."""
    ctx, rr, rid = repo_ctx()
    require_registered_repo(ctx, rid)

    rel, _src = resolve_existing_user_path(base_dir=rr, user_path=path, location="repo", action="mirror")

    owner_id = repo_owner_id(rid)
    dest_root = get_mirror_root(ctx.root, owner_id)
    if dry_run:
        return [f"would mirror: {rel} -> {dest_root / rel}"]

    count = copy_to_managed(src_root=rr, dest_root=dest_root, rel=rel, force=force)
    return [
        f"added: {count} file(s) to {dest_root / rel}",
        "hint: apply into repo with `cfg repo apply`",
    ]


def remove_path(*, path: str, dry_run: bool) -> list[str]:
    """Business logic for `cfg repo unmirror` (returns lines to print)."""
    ctx, rr, rid = repo_ctx()
    require_registered_repo(ctx, rid)

    rel = resolve_relative_user_path(rr, path)
    owner_id = repo_owner_id(rid)
    dest_root = get_mirror_root(ctx.root, owner_id)
    target, existed = safe_remove_within_root(
        root=dest_root, rel=rel, dry_run=dry_run, scope="repo mirror root"
    )

    if not existed:
        return [NO_CHANGE_NOT_MANAGED]

    if dry_run:
        return [f"would remove: {target}"]

    return [f"removed: {target}"]
