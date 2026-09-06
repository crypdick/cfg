from __future__ import annotations

import shutil

from cfg.core.cli_logic_utils import (
    format_features_list,
    normalize_feature_name,
)
from cfg.core.errors import CfgError
from cfg.core.feature_validation import (
    require_feature_exists_in_manifest,
    require_feature_not_exists_in_manifest,
)
from cfg.core.owners import (
    FeatureManifest,
    feature_manifest_to_bytes,
    resolve_host_owner_ids_for_host,
)
from cfg.core.scope import Scope
from cfg.host.cli_common import host_ctx, require_registered_host


def features_list(*, host: str | None) -> list[str]:
    """Business logic for `cfg host feature list` (returns lines to print)."""
    ctx, host = host_ctx(host)
    entry = ctx.store.get_host(host)
    if entry is None:
        return [
            "(host not registered)",
            f"hint: run `cfg host init {host}` (writes {ctx.store.get_host_path(host)})",
        ]
    return format_features_list(entry.features)


def features_add(*, feature: str, host: str | None, dry_run: bool = False) -> list[str]:
    """Business logic for `cfg host feature add` (returns lines to print)."""
    ctx, host = host_ctx(host)
    f = normalize_feature_name(feature, Scope.HOST)

    # Validate host is registered (returns its settings).
    loaded = require_registered_host(ctx, host, include_hint=True)

    # Validate feature exists in manifest (fail fast with helpful error).
    require_feature_exists_in_manifest(ctx, f, Scope.HOST)

    features = list(loaded.features)

    # Idempotent: if already enabled, succeed with message (don't error).
    if f in features:
        return [f"ok (already enabled): {f}"]

    updated = loaded.model_copy(update={"features": [*features, f]})
    path = ctx.store.get_host_path(host)
    if dry_run:
        return [f"would update: {path}"]
    path2 = ctx.store.save_host(updated)
    return [f"updated: {path2}"]


def features_remove(*, feature: str, host: str | None, dry_run: bool = False) -> list[str]:
    """Business logic for `cfg host feature remove` (returns lines to print)."""
    ctx, host = host_ctx(host)
    f = normalize_feature_name(feature, Scope.HOST)

    # Validate host is registered (returns its settings).
    loaded = require_registered_host(ctx, host, include_hint=True)

    # Validate feature exists in manifest (catch typos early).
    require_feature_exists_in_manifest(ctx, f, Scope.HOST)

    features = list(loaded.features)

    # Idempotent: if not enabled, succeed with message (don't error).
    if f not in features:
        return [f"ok (not enabled): {f}"]

    updated = loaded.model_copy(update={"features": [t for t in features if t != f]})
    path = ctx.store.get_host_path(host)
    if dry_run:
        return [f"would update: {path}"]
    path2 = ctx.store.save_host(updated)
    return [f"updated: {path2}"]


def features_create(*, feature: str, requires: list[str], dry_run: bool = False) -> list[str]:
    """
    Business logic for `cfg host feature create` (returns lines to print).

    Creates a feature directory with a feature.toml scaffold.

    Args:
        feature: Short feature name (for example, "my-feature")
        requires: Short names of required host features (for example, ["base"])
        dry_run: If True, print actions but don't create files
    """
    ctx = host_ctx(None)[0]
    f = normalize_feature_name(feature, Scope.HOST)

    # Validate feature doesn't already exist.
    require_feature_not_exists_in_manifest(ctx, f, Scope.HOST)

    feature_path = Scope.HOST.feature_dir(ctx.root, f)

    # Normalize required features (allow_base=True since base is a valid dependency)
    normalized_requires = [normalize_feature_name(r, Scope.HOST, allow_base=True) for r in requires]

    # Validate all required features exist.
    for req in normalized_requires:
        require_feature_exists_in_manifest(ctx, req, Scope.HOST)

    # Serialize from the model so the on-disk schema can't drift (and ids are
    # escaped by the TOML writer, not by hand).
    manifest = FeatureManifest(requires=normalized_requires)
    cfg_toml_path = feature_path / "feature.toml"

    if dry_run:
        return [f"would create: {feature_path}/", f"would create: {cfg_toml_path}"]

    feature_path.mkdir(parents=True)
    cfg_toml_path.write_bytes(feature_manifest_to_bytes(manifest))

    return [f"created: {feature_path}/", f"created: {cfg_toml_path}"]


def features_delete(*, feature: str, dry_run: bool = False) -> list[str]:
    """
    Business logic for `cfg host feature delete` (returns lines to print).

    Deletes a feature directory from the filesystem after verifying it's not in use.

    Safety checks:
    1. Validates feature exists
    2. Checks manifest dependencies and effective host owner sets
    3. If in use, errors and tells user to run 'remove' first
    4. If not in use, deletes the feature directory
    """
    ctx = host_ctx(None)[0]
    f = normalize_feature_name(feature, Scope.HOST)

    # Build feature path.
    feature_path = Scope.HOST.feature_dir(ctx.root, f)

    # Idempotent: if doesn't exist, succeed with message (don't error).
    if not feature_path.exists():
        return [f"ok (not found): {f}"]

    snapshot = ctx.snapshot
    owner_id = Scope.HOST.feature_id(f)
    dependents = sorted(
        owner for owner, manifest in snapshot.manifest_index.items() if owner_id in manifest.requires
    )
    if dependents:
        raise CfgError(
            f"Cannot delete feature '{f}': required by {', '.join(dependents)}. "
            "Remove those dependency declarations first."
        )
    hosts_using_feature = [
        host_name
        for host_name, entry in snapshot.inventory.hosts.items()
        if owner_id
        in resolve_host_owner_ids_for_host(
            cfg_root=ctx.root,
            cfg_inventory=snapshot.inventory,
            host_settings=entry.settings,
            manifest_index=snapshot.manifest_index,
        )
    ]

    # If any host uses it, error
    if hosts_using_feature:
        hosts_str = ", ".join(hosts_using_feature)
        raise CfgError(
            f"Cannot delete feature '{f}': in use by {len(hosts_using_feature)} host(s): {hosts_str}\n"
            f"Remove from all hosts first:\n"
            + "\n".join(f"  cfg host feature remove {f} {h}" for h in hosts_using_feature)
        )

    # Safe to delete
    if dry_run:
        return [f"would delete: {feature_path}"]

    shutil.rmtree(feature_path)
    return [f"deleted: {feature_path}"]
