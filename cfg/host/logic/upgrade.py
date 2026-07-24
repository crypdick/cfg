from __future__ import annotations

from cfg.host.cli_common import builtin_workflow_path, host_ctx, require_registered_host
from cfg.host.runner import run_pyinfra


def upgrade(*, host: str | None, dry_run: bool, quiet: bool = False) -> list[str]:
    """Refresh package metadata and install available package updates."""
    ctx, host = host_ctx(host)
    require_registered_host(ctx, host)
    run_pyinfra(
        cfg_root=ctx.root,
        cfg_inventory=ctx.store.inventory,
        limit=["@local"],
        deploy_file=builtin_workflow_path("upgrade_packages"),
        current_host_for_local=host,
        dry_run=dry_run,
        quiet=quiet,
    )
    return ["packages planned." if dry_run else "packages upgraded."]
