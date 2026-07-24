from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId
from cfg.core.owners.models import FeatureOwner, HostOwner, RepoOwner, parse_owner_ref


def _host_features_root(cfg_root: Path) -> Path:
    return (cfg_root / "features" / "host").resolve()


def _repo_features_root(cfg_root: Path) -> Path:
    return (cfg_root / "features" / "repo").resolve()


def owner_id_to_dir(cfg_root: Path, owner_id: OwnerId) -> Path:
    """
    Convert an internal owner id into its canonical data directory.
    """
    try:
        owner = parse_owner_ref(owner_id)
    except ValueError as e:
        raise CfgError(str(e)) from e
    if isinstance(owner, FeatureOwner):
        root = _host_features_root(cfg_root) if owner.scope.value == "host" else _repo_features_root(cfg_root)
        return root / owner.name
    if isinstance(owner, HostOwner):
        return cfg_root / "hosts" / owner.name
    if isinstance(owner, RepoOwner):
        return cfg_root / "repos" / Path(owner.repo_id)
    raise AssertionError(f"Unhandled owner: {owner!r}")


def get_mirror_root(cfg_root: Path, owner_id: OwnerId) -> Path:
    """Directory holding an owner's mirrored (managed) payload files."""
    return owner_id_to_dir(cfg_root, owner_id) / "mirror"


def feature_manifest_path(cfg_root: Path, owner_id: OwnerId) -> Path:
    """Return the metadata path for a scoped feature owner id."""
    try:
        owner = parse_owner_ref(owner_id)
    except ValueError as e:
        raise CfgError(str(e)) from e
    if not isinstance(owner, FeatureOwner):
        raise CfgError(f"Not a feature owner id: {owner_id!r}")
    return owner_id_to_dir(cfg_root, owner.id) / "feature.toml"
