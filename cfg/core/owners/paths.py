from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.models import safe_relpath


def _host_features_root(cfg_root: Path) -> Path:
    return (cfg_root / "features" / "host").resolve()


def _repo_features_root(cfg_root: Path) -> Path:
    return (cfg_root / "features" / "repo").resolve()


def owner_id_to_dir(cfg_root: Path, owner_id: str) -> Path:
    """
    Convert an internal owner id into its canonical data directory.
    """
    rel = safe_relpath(owner_id)
    parts = list(rel.parts)
    if not parts:
        raise CfgError(f"Invalid owner id: {owner_id!r}")
    scope = parts[0]
    if scope not in {"host", "repo"}:
        raise CfgError(f"Invalid owner id scope (expected host/ or repo/): {owner_id!r}")
    if len(parts) >= 2 and parts[1] == "feature":
        if len(parts) != 3:
            raise CfgError(f"Invalid feature owner id: {owner_id!r}")
        root = _host_features_root(cfg_root) if scope == "host" else _repo_features_root(cfg_root)
        return root / parts[2]
    if scope == "host" and len(parts) == 2:
        return cfg_root / "hosts" / parts[1]
    if scope == "repo" and len(parts) == 3:
        return cfg_root / "repos" / parts[1] / parts[2]
    raise CfgError(f"Invalid {scope} owner id: {owner_id!r}")


def get_mirror_root(cfg_root: Path, owner_id: str) -> Path:
    """Directory holding an owner's mirrored (managed) payload files."""
    return owner_id_to_dir(cfg_root, owner_id) / "mirror"


def feature_manifest_path(cfg_root: Path, owner_id: str) -> Path:
    """Return the metadata path for a scoped feature owner id."""
    oid = str(owner_id).strip()
    if not oid.startswith(("host/feature/", "repo/feature/")):
        raise CfgError(f"Not a feature owner id: {owner_id!r}")
    return owner_id_to_dir(cfg_root, oid) / "feature.toml"
