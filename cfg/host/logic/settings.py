from __future__ import annotations

from cfg.core.owners import resolve_host_owner_ids_for_host
from cfg.host.cli_common import host_ctx


def settings(*, host: str | None) -> list[str]:
    """Business logic for `cfg host settings` (returns lines to print)."""
    ctx, host = host_ctx(host)
    entry = ctx.store.get_host(host)
    if not entry:
        return ["(host not registered)"]
    owners = resolve_host_owner_ids_for_host(
        cfg_root=ctx.root, cfg_inventory=ctx.store.inventory, host_settings=entry
    )
    return [
        str(entry),
        "",
        f"features:          {list(entry.features)}",
        f"owners_resolved:   {owners}",
    ]
