"""
Resolve host "home files" from two sources:

- Feature payloads:    features/host/*/overlay/<path-inside-home>
- Host-specific files: hosts/<host>/overlay/<path-inside-home>

Precedence:
- Host-specific files override owner-provided files.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.ids import HostName, OwnerId
from cfg.core.owners import OwnerManifest, load_owner_manifest_index
from cfg.host.fs import HOST_HOME_PROVIDER, host_specific_home_files
from cfg.owners.fs import OwnerFile, owner_overlay_files
from cfg.owners.providers import select_path_providers


@dataclass(frozen=True)
class HomePlan:
    desired: dict[Path, OwnerFile]  # rel -> provider file
    all_known_rels: set[Path]


def resolve_host_home_plan(
    *,
    cfg_root: Path,
    host: HostName,
    enabled_owner_ids: Sequence[OwnerId],
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
) -> HomePlan:
    if manifest_index is None:
        manifest_index = load_owner_manifest_index(cfg_root)

    host_owner = OwnerId(f"host/{host}")
    payloads = {
        owner: owner_overlay_files(cfg_root=cfg_root, owner_id=owner)
        for owner in manifest_index
        if owner != host_owner
    }
    providers: dict[Path, list[OwnerFile]] = {}
    for owner in dict.fromkeys(enabled_owner_ids):
        if owner == host_owner:
            continue
        if owner not in payloads:
            raise CfgError(f"Unknown owner (not in manifest index): {owner}")
        for file in payloads[owner]:
            providers.setdefault(file.rel, []).append(file)

    host_files = host_specific_home_files(cfg_root, host)
    for file in host_files:
        providers.setdefault(file.rel, []).append(file)
    desired = select_path_providers(
        providers,
        path_provider_overrides={str(file.rel): HOST_HOME_PROVIDER for file in host_files},
        conflict_error_prefix="Home owner conflict",
    )
    all_rels = {file.rel for files in payloads.values() for file in files}
    all_rels.update(file.rel for file in host_files)
    return HomePlan(desired=desired, all_known_rels=all_rels)


def managed_home_roots(cfg_root: Path) -> list[Path]:
    """
    Roots used as "ownership markers" for managed symlinks.
    """
    return [
        (cfg_root / "features" / "host").resolve(),
        (cfg_root / "hosts").resolve(),
    ]
