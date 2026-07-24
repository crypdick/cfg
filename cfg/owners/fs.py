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

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.fs import iter_files
from cfg.core.owners import load_owner_manifest_index, owner_id_to_dir
from cfg.core.special_files import logical_rel_from_storage_rel


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


def owner_overlay_files(*, cfg_root: Path, owner_id: str) -> list[OwnerFile]:
    owner_dir = owner_id_to_dir(cfg_root, owner_id)
    pairs = _owner_payload_files(owner_dir=owner_dir, mode_dirname="overlay")
    return [OwnerFile(owner=owner_id, src=src, rel=rel) for src, rel in pairs]


def owner_mirror_files(*, cfg_root: Path, owner_id: str) -> list[OwnerFile]:
    owner_dir = owner_id_to_dir(cfg_root, owner_id)
    pairs = _owner_payload_files(owner_dir=owner_dir, mode_dirname="mirror")
    return [OwnerFile(owner=owner_id, src=src, rel=rel) for src, rel in pairs]


def owner_render_root(*, cfg_root: Path, owner_id: str) -> Path:
    return owner_id_to_dir(cfg_root, owner_id) / "render"


@dataclass(frozen=True)
class ResolvedOwnerFiles:
    """Result of resolving owner-provided files with conflict handling."""

    desired: dict[Path, OwnerFile]
    all_known_rels: set[Path]


def resolve_owner_files(
    *,
    cfg_root: Path,
    enabled_owner_ids: list[str],
    file_getter: Callable[[Path, str], list[OwnerFile]],
    path_provider_overrides: dict[str, str] | None = None,
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
        ResolvedOwnerFiles with desired files and all known relpaths
    """
    path_provider_overrides = dict(path_provider_overrides or {})
    manifest_index = load_owner_manifest_index(cfg_root)

    # Collect providers per rel path.
    providers: dict[Path, list[OwnerFile]] = {}
    for owner_id in enabled_owner_ids or []:
        if owner_id not in manifest_index:
            raise CfgError(f"Unknown owner (not in manifest index): {owner_id}")
        for of in file_getter(cfg_root, owner_id):
            providers.setdefault(of.rel, []).append(of)

    desired: dict[Path, OwnerFile] = {}
    conflicts: list[str] = []

    for rel, tfs in sorted(providers.items(), key=lambda kv: str(kv[0])):
        if len(tfs) == 1:
            desired[rel] = tfs[0]
            continue

        override = path_provider_overrides.get(str(rel))
        if override:
            matches = [tf for tf in tfs if tf.owner == override]
            if len(matches) == 1:
                desired[rel] = matches[0]
                continue
            providers_list = ", ".join(sorted({tf.owner for tf in tfs}))
            conflicts.append(f"{rel} (override={override!r} not among providers: {providers_list})")
            continue

        providers_list = ", ".join(sorted({tf.owner for tf in tfs}))
        conflicts.append(f"{rel} (multiple providers: {providers_list})")

    if conflicts:
        msg = "\n".join(f"- {c}" for c in conflicts)
        raise CfgError(
            f"{conflict_error_prefix} detected between enabled owners:\n"
            f"{msg}\n\n"
            "Fix by:\n"
            "- removing one of the conflicting owners, or\n"
            "- adding an explicit path provider override in settings\n"
        )

    # Collect all known rels (for stale cleanup).
    all_rels: set[Path] = set()
    for owner_id in manifest_index:
        for of in file_getter(cfg_root, owner_id):
            all_rels.add(of.rel)

    return ResolvedOwnerFiles(desired=desired, all_known_rels=all_rels)
