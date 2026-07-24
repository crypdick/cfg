from __future__ import annotations

from cfg.core.context import CfgContext
from cfg.core.host_id import find_cfg_host
from cfg.host.cli_common import resolve_workflow_path
from cfg.host.runner import resolve_targets, run_pyinfra


def run_workflow(*, workflow: str, hosts: str, dry_run: bool = False) -> list[str]:
    """Business logic for `cfg host run`."""
    ctx = CfgContext.load()
    limit = resolve_targets(ctx.store.inventory, hosts)
    deploy = resolve_workflow_path(ctx.root, workflow)
    current = find_cfg_host()
    run_pyinfra(
        cfg_root=ctx.root,
        cfg_inventory=ctx.store.inventory,
        limit=limit,
        deploy_file=deploy,
        current_host_for_local=current,
        dry_run=dry_run,
    )
    return []
