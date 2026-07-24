"""Load feature metadata and expose it through the internal owner resolver."""

from __future__ import annotations

import tomllib
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId
from cfg.core.inventory import Inventory, load_inventory
from cfg.core.owners.models import (
    FeatureManifest,
    FeatureOwner,
    OwnerManifest,
    default_owner_manifest,
    owner_id_from_feature_toml_path,
    parse_owner_ref,
)
from cfg.core.owners.paths import _host_features_root, _repo_features_root
from cfg.core.scope import Scope


def _load_feature_manifest(path: Path, *, owner_id: OwnerId) -> OwnerManifest:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, PermissionError, OSError, tomllib.TOMLDecodeError) as e:
        raise CfgError(f"Failed to read feature manifest: {path}\n{e}") from e

    try:
        feature = FeatureManifest.model_validate(data)
    except (TypeError, ValueError) as e:
        raise CfgError(f"Invalid feature manifest content: {path}\n{e}") from e

    owner = parse_owner_ref(owner_id)
    if not isinstance(owner, FeatureOwner):
        raise CfgError(f"Invalid feature owner id: {owner_id}")
    if owner.scope is Scope.HOST:
        if feature.host_requires:
            raise CfgError(f"Host feature cannot declare host_requires: {path}")
        if feature.generated:
            raise CfgError(f"Host feature cannot declare generated outputs: {path}")

    requires = [FeatureOwner(scope=owner.scope, name=name).id for name in feature.requires]
    if owner.scope is Scope.REPO:
        requires.extend(FeatureOwner(scope=Scope.HOST, name=name).id for name in feature.host_requires)
    conflicts = [FeatureOwner(scope=owner.scope, name=name).id for name in feature.conflicts]
    return OwnerManifest(
        owner=owner,
        requires=tuple(requires),
        conflicts=tuple(conflicts),
        generated=tuple(feature.generated),
    )


def load_owner_manifest_index(
    cfg_root: Path,
    *,
    inventory: Inventory | None = None,
) -> dict[OwnerId, OwnerManifest]:
    """Load feature manifests plus implicit host/repo-specific owners."""
    out: dict[OwnerId, OwnerManifest] = {}
    roots = [
        _host_features_root(cfg_root),
        _repo_features_root(cfg_root),
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("feature.toml")):
            if not path.is_file():
                continue
            try:
                owner_id = owner_id_from_feature_toml_path(cfg_root=cfg_root, path=path)
            except ValueError as e:
                raise CfgError(str(e)) from e
            if owner_id in out:
                raise CfgError(f"Duplicate feature manifest: {owner_id}\n- {path}")
            out[owner_id] = _load_feature_manifest(path, owner_id=owner_id)

    if inventory is None:
        inventory = load_inventory(cfg_root)
    for host_name in sorted(inventory.hosts):
        owner_id = parse_owner_ref(f"host/{host_name}").id
        out.setdefault(owner_id, default_owner_manifest(owner_id))
    for repo_id in sorted(inventory.repos):
        owner_id = parse_owner_ref(f"repo/{repo_id}").id
        out.setdefault(owner_id, default_owner_manifest(owner_id))
    return out
