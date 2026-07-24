from __future__ import annotations

from cfg.core.context import CfgContext
from cfg.core.host_id import find_cfg_host
from cfg.host.runner import resolve_targets, run_pyinfra_debug_inventory


def debug_inventory(*, hosts: str | None, print_generated: bool, run: bool) -> str | None:
    """Business logic for `cfg host debug-inventory` (returns optional generated text)."""
    ctx = CfgContext.load()
    current = find_cfg_host()

    limit = resolve_targets(ctx.store.inventory, hosts) if hosts else None

    if print_generated:
        from cfg.pyinfra.runtime_inventory import cleanup_runtime_inventory, write_runtime_inventory

        include_local = "@local" in (limit or [])
        inv_path, tmpdir = write_runtime_inventory(
            cfg_root=ctx.root,
            cfg_inventory=ctx.store.inventory,
            current_host_for_local=current,
            include_local=include_local,
        )
        try:
            generated_text = inv_path.read_text(encoding="utf-8")
        finally:
            cleanup_runtime_inventory(tmpdir)
    else:
        generated_text = None

    if run:
        run_pyinfra_debug_inventory(
            cfg_root=ctx.root,
            cfg_inventory=ctx.store.inventory,
            limit=limit,
            current_host_for_local=current,
        )
    return generated_text
