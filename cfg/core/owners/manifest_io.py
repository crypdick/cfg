"""Load feature metadata and expose it through the internal owner resolver."""

from __future__ import annotations

import tomllib
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.owners.models import (
    FeatureManifest,
    OwnerDeps,
    OwnerInfo,
    OwnerManifest,
    default_owner_manifest,
    owner_id_from_feature_toml_path,
)
from cfg.core.owners.paths import _host_features_root, _repo_features_root
from cfg.core.scope import Scope


def _load_feature_manifest(path: Path, *, owner_id: str) -> OwnerManifest:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, PermissionError, OSError, tomllib.TOMLDecodeError) as e:
        raise CfgError(f"Failed to read feature manifest: {path}\n{e}") from e

    try:
        feature = FeatureManifest.model_validate(data)
    except (TypeError, ValueError) as e:
        raise CfgError(f"Invalid feature manifest content: {path}\n{e}") from e

    if owner_id.startswith(Scope.HOST.feature_prefix):
        scope = Scope.HOST
        if feature.host_requires:
            raise CfgError(f"Host feature cannot declare host_requires: {path}")
    elif owner_id.startswith(Scope.REPO.feature_prefix):
        scope = Scope.REPO
    else:
        raise CfgError(f"Invalid feature owner id: {owner_id}")

    requires = [scope.feature_id(name) for name in feature.requires]
    if scope is Scope.REPO:
        requires.extend(Scope.HOST.feature_id(name) for name in feature.host_requires)
    conflicts = [scope.feature_id(name) for name in feature.conflicts]
    return OwnerManifest(
        owner=OwnerInfo(id=owner_id),
        deps=OwnerDeps(requires=requires, conflicts=conflicts),
        generated=feature.generated,
    )


def load_owner_manifest_index(cfg_root: Path) -> dict[str, OwnerManifest]:
    """Load feature manifests plus implicit host/repo-specific owners."""
    out: dict[str, OwnerManifest] = {}
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

    from cfg.core.inventory import load_inventory

    inventory = load_inventory(cfg_root)
    for host_name in sorted(inventory.hosts):
        out.setdefault(f"host/{host_name}", default_owner_manifest(f"host/{host_name}"))
    for repo_id in sorted(inventory.repos):
        out.setdefault(f"repo/{repo_id}", default_owner_manifest(f"repo/{repo_id}"))
    return out
