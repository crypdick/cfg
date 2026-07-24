"""
Owner system core.

- owner ids: `repo/...`, `repo/feature/...`, `host/...`, `host/feature/...`
- canonical bytes live under `features/`, `hosts/`, and `repos/`
- feature owners have a small `feature.toml` metadata file
- host- and repo-specific owners are inferred from inventory settings
- payload directories define overlay and mirror paths directly
"""

from __future__ import annotations

# Keep owner-system imports available from one module.
from cfg.core.owners.manifest_io import load_owner_manifest_index
from cfg.core.owners.manifest_write import (
    feature_manifest_to_bytes,
)
from cfg.core.owners.models import (
    FeatureManifest,
    OwnerDeps,
    OwnerInfo,
    OwnerManifest,
    default_owner_manifest,
    owner_id_from_feature_toml_path,
)
from cfg.core.owners.paths import (
    feature_manifest_path,
    get_mirror_root,
    owner_id_to_dir,
)
from cfg.core.owners.resolution import (
    resolve_host_owner_ids_for_host,
    resolve_host_owner_ids_implied_by_repo,
    resolve_owners,
    resolve_owners_scoped,
    resolve_repo_owner_ids,
)

__all__ = [
    "FeatureManifest",
    "OwnerDeps",
    "OwnerInfo",
    "OwnerManifest",
    "default_owner_manifest",
    "feature_manifest_path",
    "feature_manifest_to_bytes",
    "get_mirror_root",
    "load_owner_manifest_index",
    "owner_id_from_feature_toml_path",
    "owner_id_to_dir",
    "resolve_host_owner_ids_for_host",
    "resolve_host_owner_ids_implied_by_repo",
    "resolve_owners",
    "resolve_owners_scoped",
    "resolve_repo_owner_ids",
]
