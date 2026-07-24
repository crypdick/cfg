from __future__ import annotations

from pathlib import Path

from cfg.core.owners import load_owner_manifest_index, resolve_host_owner_ids_for_host
from cfg.host.cli_common import host_ctx, require_registered_host
from cfg.host.fs import host_specific_home_files
from cfg.owners.fs import owner_overlay_files, resolve_owner_files
from cfg.render.generated import resolve_generated_targets
from cfg.render.managed_report import format_managed_sections, generated_sources


def managed(*, host: str | None) -> list[str]:
    """Business logic for `cfg host managed` (returns lines to print)."""
    ctx, host = host_ctx(host)
    settings = require_registered_host(ctx, host, include_hint=True)

    manifest_index = load_owner_manifest_index(ctx.root)
    owner_ids = [
        o
        for o in resolve_host_owner_ids_for_host(
            cfg_root=ctx.root, cfg_inventory=ctx.store.inventory, host_settings=settings
        )
        if o in manifest_index
    ]

    # linked: owner overlay files that apply into home
    linked_resolved = resolve_owner_files(
        cfg_root=ctx.root,
        enabled_owner_ids=owner_ids,
        file_getter=lambda cfg, owner_id: owner_overlay_files(cfg_root=cfg, owner_id=owner_id),
        path_provider_overrides=None,
        conflict_error_prefix="Home owner conflict",
    )

    # mirrored: host-specific managed payload captured via `cfg host mirror`
    mirrored_files = host_specific_home_files(ctx.root, host)
    mirrored: dict[Path, object] = {tf.rel: tf for tf in mirrored_files}

    # generated: declared generated outputs (template source shown)
    gt = resolve_generated_targets(
        cfg_root=ctx.root,
        enabled_owner_ids=owner_ids,
        path_provider_overrides=None,
        conflict_error_prefix="Generated artifact conflict",
    )

    generated = generated_sources(cfg_root=ctx.root, desired_targets=gt.desired)

    return format_managed_sections(
        linked=linked_resolved.desired,
        mirrored=mirrored,
        generated=generated,
    )
