"""
Owner payload filesystem helpers.

Canonical bytes live under:
- host features: features/host/<name>/{overlay,mirror,render}/**
- repo features: features/repo/<name>/{overlay,mirror,render}/**
- host-specific owners: hosts/<name>/{overlay,mirror,render}/**
- repo-specific owners: repos/<owner>/<repo>/{overlay,mirror,render}/**

Destination relpaths are inferred directly from the files under `overlay/` and
`mirror/`; metadata does not duplicate the payload file list.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.fs import iter_files
from cfg.core.ids import OwnerId
from cfg.core.owners import OwnerManifest, load_owner_manifest_index, owner_id_to_dir
from cfg.core.special_files import logical_rel_from_storage_rel
from cfg.owners.providers import select_path_providers


@dataclass(frozen=True)
class OwnerFile:
    owner: str
    src: Path
    rel: Path  # relative to repo root (or home root for host/home files)


def _owner_payload_files(*, owner_dir: Path, mode_dirname: str) -> list[tuple[Path, Path]]:
    """Return every payload file and its logical destination path."""
    mode_root = owner_dir / mode_dirname
    return [
        (source, logical_rel_from_storage_rel(source.relative_to(mode_root)))
        for source in iter_files(mode_root)
    ]


def owner_overlay_files(*, cfg_root: Path, owner_id: OwnerId) -> list[OwnerFile]:
    owner_dir = owner_id_to_dir(cfg_root, owner_id)
    pairs = _owner_payload_files(owner_dir=owner_dir, mode_dirname="overlay")
    return [OwnerFile(owner=owner_id, src=src, rel=rel) for src, rel in pairs]


def owner_mirror_files(*, cfg_root: Path, owner_id: OwnerId) -> list[OwnerFile]:
    owner_dir = owner_id_to_dir(cfg_root, owner_id)
    pairs = _owner_payload_files(owner_dir=owner_dir, mode_dirname="mirror")
    return [OwnerFile(owner=owner_id, src=src, rel=rel) for src, rel in pairs]


def owner_render_root(*, cfg_root: Path, owner_id: OwnerId) -> Path:
    return owner_id_to_dir(cfg_root, owner_id) / "render"


@dataclass(frozen=True)
class ResolvedOwnerFiles:
    """Result of resolving owner-provided files with conflict handling."""

    desired: dict[Path, OwnerFile]


def resolve_owner_files(
    *,
    cfg_root: Path,
    enabled_owner_ids: Sequence[OwnerId],
    file_getter: Callable[[Path, OwnerId], list[OwnerFile]],
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
    path_provider_overrides: Mapping[str, str] | None = None,
    conflict_error_prefix: str = "Owner file conflict",
) -> ResolvedOwnerFiles:
    """
    Resolve owner-provided files with conflict detection and override support.

    Args:
        cfg_root: Path to the personalization repository root
        enabled_owner_ids: List of owner IDs to collect files from
        file_getter: Function to get files from an owner (e.g. owner_overlay_files or owner_mirror_files)
        path_provider_overrides: Optional map of relpath -> owner_id to resolve conflicts
        conflict_error_prefix: Prefix for error message on conflicts

    Returns:
        ResolvedOwnerFiles with selected desired files
    """
    path_provider_overrides = dict(path_provider_overrides or {})
    if manifest_index is None:
        manifest_index = load_owner_manifest_index(cfg_root)

    # Collect providers per rel path.
    providers: dict[Path, list[OwnerFile]] = {}
    for owner_id in enabled_owner_ids or []:
        if owner_id not in manifest_index:
            raise CfgError(f"Unknown owner (not in manifest index): {owner_id}")
        for of in file_getter(cfg_root, owner_id):
            providers.setdefault(of.rel, []).append(of)

    desired = select_path_providers(
        providers,
        path_provider_overrides=path_provider_overrides,
        conflict_error_prefix=conflict_error_prefix,
    )

    return ResolvedOwnerFiles(desired=desired)
