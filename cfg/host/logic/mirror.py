from __future__ import annotations

from pathlib import Path

from cfg.core.cli_helpers import (
    copy_to_managed,
    resolve_existing_user_path,
    resolve_relative_user_path,
    safe_remove_within_root,
)
from cfg.core.cli_logic_utils import NO_CHANGE_NOT_MANAGED
from cfg.host.cli_common import host_ctx, require_registered_host
from cfg.host.fs import host_home_root


def add_path(*, path: str, host: str | None, force: bool, dry_run: bool) -> list[str]:
    """Business logic for `cfg host mirror` (returns lines to print)."""
    ctx, host = host_ctx(host)
    require_registered_host(ctx, host)

    home_dir = Path.home().resolve()
    rel, _src = resolve_existing_user_path(
        base_dir=home_dir,
        user_path=path,
        location="home",
        action="mirror",
        expand_user=True,
    )

    dest_root = host_home_root(ctx.root, host)
    if dry_run:
        return [f"would mirror: ~/{rel.as_posix()} -> {dest_root / rel}"]

    count = copy_to_managed(src_root=home_dir, dest_root=dest_root, rel=rel, force=force)
    return [
        f"added: {count} file(s) to {dest_root / rel}",
        "hint: apply into home with `cfg host apply`",
    ]


def remove_path(*, path: str, host: str | None, dry_run: bool) -> list[str]:
    """Business logic for `cfg host unmirror` (returns lines to print)."""
    ctx, host = host_ctx(host)
    require_registered_host(ctx, host)

    dest_root = host_home_root(ctx.root, host)
    home_dir = Path.home().resolve()
    rel = resolve_relative_user_path(base_dir=home_dir, user_path=path, expand_user=True)
    target, existed = safe_remove_within_root(
        root=dest_root,
        rel=rel,
        dry_run=dry_run,
        scope="host home payload root",
    )

    if not existed:
        return [NO_CHANGE_NOT_MANAGED]

    if dry_run:
        return [f"would remove: {target}"]
    return [f"removed: {target}"]
