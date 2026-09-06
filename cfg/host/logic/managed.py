from __future__ import annotations

from cfg.core.owners import resolve_host_owner_ids_for_host
from cfg.host.cli_common import host_ctx, require_registered_host
from cfg.host.fs import HOST_HOME_PROVIDER
from cfg.host.managed_home import resolve_host_home_plan
from cfg.render.managed_report import format_managed_sections


def managed(*, host: str | None) -> list[str]:
    """Business logic for `cfg host managed` (returns lines to print)."""
    ctx, host = host_ctx(host)
    settings = require_registered_host(ctx, host, include_hint=True)

    snapshot = ctx.snapshot
    owner_ids = resolve_host_owner_ids_for_host(
        cfg_root=ctx.root,
        cfg_inventory=snapshot.inventory,
        host_settings=settings,
        manifest_index=snapshot.manifest_index,
    )

    # linked: owner overlay files that apply into home
    linked_resolved = resolve_host_home_plan(
        host=settings.name,
        cfg_root=ctx.root,
        enabled_owner_ids=owner_ids,
        manifest_index=snapshot.manifest_index,
    )

    return format_managed_sections(
        linked={
            rel: file for rel, file in linked_resolved.desired.items() if file.owner != HOST_HOME_PROVIDER
        },
        mirrored={
            rel: file for rel, file in linked_resolved.desired.items() if file.owner == HOST_HOME_PROVIDER
        },
    )
