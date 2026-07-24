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
from cfg.core.fs import iter_files
from cfg.core.ids import HostName, OwnerId
from cfg.core.owners import OwnerManifest, load_owner_manifest_index
from cfg.host.fs import host_home_root, host_specific_home_files
from cfg.owners.fs import OwnerFile, owner_overlay_files


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
    desired: dict[Path, OwnerFile] = {}

    if manifest_index is None:
        manifest_index = load_owner_manifest_index(cfg_root)

    # Owner-provided home overlay files.
    providers_by_rel: dict[Path, list[OwnerId]] = {}
    for owner_id in enabled_owner_ids or []:
        if owner_id not in manifest_index:
            raise CfgError(f"Unknown owner (not in manifest index): {owner_id}")
        for of in owner_overlay_files(cfg_root=cfg_root, owner_id=owner_id):
            providers_by_rel.setdefault(of.rel, []).append(owner_id)
            desired[of.rel] = of

    # Hard error on multiple providers (single-provider invariant).
    conflicts = sorted(
        [rel for rel, owners in providers_by_rel.items() if len(set(owners)) > 1], key=lambda p: p.as_posix()
    )
    if conflicts:
        msg = "\n".join(f"- {rel} (providers={sorted(set(providers_by_rel[rel]))})" for rel in conflicts)
        raise CfgError(f"Home owner conflict detected:\n{msg}")

    # Host-specific overrides win.
    for tf in host_specific_home_files(cfg_root, host):
        desired[tf.rel] = tf

    all_rels: set[Path] = set()

    # Track all owner-provided home files (for stale symlink cleanup).
    for owner_id in manifest_index:
        for of in owner_overlay_files(cfg_root=cfg_root, owner_id=owner_id):
            all_rels.add(of.rel)

    # Track all host-specific home files too.
    host_root = host_home_root(cfg_root, host)
    for src in iter_files(host_root):
        all_rels.add(src.relative_to(host_root))

    return HomePlan(desired=desired, all_known_rels=all_rels)


def managed_home_roots(cfg_root: Path) -> list[Path]:
    """
    Roots used as "ownership markers" for managed symlinks.
    """
    return [
        (cfg_root / "features" / "host").resolve(),
        (cfg_root / "hosts").resolve(),
    ]
