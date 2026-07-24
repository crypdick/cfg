from __future__ import annotations

from pathlib import Path

from cfg.core.owners import resolve_host_owner_ids_for_host
from cfg.host.cli_common import host_ctx, require_registered_host
from cfg.host.fs import host_specific_home_files
from cfg.owners.fs import owner_overlay_files, resolve_owner_files
from cfg.render.managed_report import format_managed_sections


def managed(*, host: str | None) -> list[str]:
    """Business logic for `cfg host managed` (returns lines to print)."""
    ctx, host = host_ctx(host)
    settings = require_registered_host(ctx, host, include_hint=True)

    snapshot = ctx.snapshot
    owner_ids = [
        o
        for o in resolve_host_owner_ids_for_host(
            cfg_root=ctx.root,
            cfg_inventory=snapshot.inventory,
            host_settings=settings,
            manifest_index=snapshot.manifest_index,
        )
        if o in snapshot.manifest_index
    ]

    # linked: owner overlay files that apply into home
    linked_resolved = resolve_owner_files(
        cfg_root=ctx.root,
        enabled_owner_ids=owner_ids,
        file_getter=lambda cfg, owner_id: owner_overlay_files(cfg_root=cfg, owner_id=owner_id),
        manifest_index=snapshot.manifest_index,
        path_provider_overrides=None,
        conflict_error_prefix="Home owner conflict",
    )

    # mirrored: host-specific managed payload captured via `cfg host mirror`
    mirrored_files = host_specific_home_files(ctx.root, host)
    mirrored: dict[Path, object] = {tf.rel: tf for tf in mirrored_files}

    return format_managed_sections(
        linked=linked_resolved.desired,
        mirrored=mirrored,
    )
