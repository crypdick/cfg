"""Plan and apply repo-managed files without an orchestration layer."""

from __future__ import annotations

import hashlib
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId
from cfg.core.models import ManagedPathState, RepoStateManifest, safe_managed_relpath
from cfg.core.owners import OwnerManifest
from cfg.core.state import read_repo_state, write_repo_state
from cfg.owners.fs import (
    OwnerFile,
    ResolvedOwnerFiles,
    owner_mirror_files,
    owner_overlay_files,
    resolve_owner_files,
)
from cfg.render.generated import (
    TemplateWrite,
    render_repo_generated_template_writes,
    render_template_write_to_string,
)


@dataclass(frozen=True)
class RemoveOverlay:
    rel: Path
    expected_target: Path


@dataclass(frozen=True)
class RemoveManaged:
    owner: str
    kind: str
    rel: Path
    expected_digest: str


@dataclass(frozen=True)
class LinkOverlay:
    owner: str
    rel: Path
    src: Path


@dataclass(frozen=True)
class WriteFile:
    owner: str
    kind: Literal["mirror", "generated"]
    rel: Path
    content: bytes
    mode: int
    source: str


RepoOperation = RemoveOverlay | RemoveManaged | LinkOverlay | WriteFile


@dataclass(frozen=True)
class RepoApplyPlan:
    """A complete, validated set of repo filesystem operations."""

    cfg_root: Path
    repo_root: Path
    operations: tuple[RepoOperation, ...]
    managed: dict[str, ManagedPathState] = field(default_factory=dict)


@dataclass(frozen=True)
class RepoOutputs:
    """Configuration-derived repo outputs, before considering a working tree."""

    overlays: ResolvedOwnerFiles
    mirrors: ResolvedOwnerFiles
    generated: tuple[TemplateWrite, ...]


def _overlay_file_getter(
    cfg_root: Path,
    owner_id: OwnerId,
) -> list[OwnerFile]:
    return owner_overlay_files(cfg_root=cfg_root, owner_id=owner_id)


def _mirror_file_getter(
    cfg_root: Path,
    owner_id: OwnerId,
) -> list[OwnerFile]:
    return owner_mirror_files(cfg_root=cfg_root, owner_id=owner_id)


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _safe_destination(*, repo_root: Path, rel: Path) -> Path:
    try:
        normalized = safe_managed_relpath(rel.as_posix())
    except ValueError as e:
        raise CfgError(str(e)) from e
    return repo_root / normalized


def _resolved_link_target(path: Path) -> Path:
    target = path.readlink()
    if not target.is_absolute():
        target = path.parent / target
    return target.resolve(strict=False)


def _validate_source(*, cfg_root: Path, source: Path, label: str) -> Path:
    resolved = source.resolve()
    try:
        resolved.relative_to(cfg_root.resolve())
    except ValueError as e:
        raise CfgError(f"{label} source escapes the cfg data root: {source}") from e
    if not resolved.is_file():
        raise CfgError(f"{label} source is not a file: {source}")
    return resolved


def _validate_parent_path(*, repo_root: Path, rel: Path, conflicts: list[str]) -> None:
    current = repo_root
    for part in rel.parts[:-1]:
        current /= part
        if current.is_symlink():
            conflicts.append(f"{rel} (parent path is a symlink: {current.relative_to(repo_root)})")
            return
        if current.exists() and not current.is_dir():
            conflicts.append(f"{rel} (parent path is not a directory: {current.relative_to(repo_root)})")
            return


def _validate_no_nested_destinations(desired: dict[Path, str], conflicts: list[str]) -> None:
    rels = set(desired)
    for rel in sorted(rels, key=lambda path: path.as_posix()):
        for parent in rel.parents:
            if parent == Path():
                break
            if parent in rels:
                conflicts.append(
                    f"{rel} ({desired[rel]} destination is nested below "
                    f"{desired[parent]} destination {parent})"
                )
                break


def _validate_remove_managed(
    *,
    operation: RemoveManaged,
    dest: Path,
    conflicts: list[str],
) -> None:
    if not dest.exists() and not dest.is_symlink():
        return
    if dest.is_symlink() or not dest.is_file():
        conflicts.append(f"{operation.rel} (stale managed destination is not a regular file)")
    elif _digest_file(dest) != operation.expected_digest:
        conflicts.append(f"{operation.rel} (stale {operation.kind} was modified after cfg last applied it)")


def resolve_repo_outputs(
    *,
    cfg_root: Path,
    repo_id: str,
    enabled_owner_ids: Sequence[OwnerId],
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
    path_provider_overrides: Mapping[str, str] | None = None,
) -> RepoOutputs:
    """Resolve and validate all configured outputs without touching a repo."""
    overrides = dict(path_provider_overrides or {})
    overlays = resolve_owner_files(
        cfg_root=cfg_root,
        enabled_owner_ids=enabled_owner_ids,
        file_getter=_overlay_file_getter,
        manifest_index=manifest_index,
        path_provider_overrides=overrides,
        conflict_error_prefix="Overlay conflict",
    )
    mirrors = resolve_owner_files(
        cfg_root=cfg_root,
        enabled_owner_ids=enabled_owner_ids,
        file_getter=_mirror_file_getter,
        manifest_index=manifest_index,
        path_provider_overrides=overrides,
        conflict_error_prefix="Mirror conflict",
    )
    generated = tuple(
        render_repo_generated_template_writes(
            cfg_root=cfg_root,
            repo_id=repo_id,
            enabled_owner_ids=enabled_owner_ids,
            manifest_index=manifest_index,
            path_provider_overrides=overrides,
        )
    )

    desired_kinds: dict[Path, str] = {}
    conflicts: list[str] = []
    for kind, rels in (
        ("overlay", overlays.desired),
        ("mirror", mirrors.desired),
        ("generated", {write.rel: write for write in generated}),
    ):
        for rel in rels:
            _safe_destination(repo_root=Path(), rel=rel)
            previous = desired_kinds.get(rel)
            if previous is not None:
                conflicts.append(f"{rel} ({previous} vs {kind})")
            else:
                desired_kinds[rel] = kind
    _validate_no_nested_destinations(desired_kinds, conflicts)
    if conflicts:
        details = "\n".join(f"- {conflict}" for conflict in sorted(set(conflicts)))
        raise CfgError(f"Repo output conflict detected:\n{details}")

    return RepoOutputs(
        overlays=overlays,
        mirrors=mirrors,
        generated=generated,
    )


def _validate_operations(plan: RepoApplyPlan) -> None:
    conflicts: list[str] = []
    for operation in plan.operations:
        dest = _safe_destination(repo_root=plan.repo_root, rel=operation.rel)
        _validate_parent_path(repo_root=plan.repo_root, rel=operation.rel, conflicts=conflicts)

        if isinstance(operation, RemoveOverlay):
            if (dest.exists() or dest.is_symlink()) and not (
                dest.is_symlink() and _resolved_link_target(dest) == operation.expected_target
            ):
                conflicts.append(f"{operation.rel} (stale overlay is no longer a cfg-owned symlink)")
            continue

        if isinstance(operation, RemoveManaged):
            _validate_remove_managed(operation=operation, dest=dest, conflicts=conflicts)
            continue

        if isinstance(operation, LinkOverlay):
            if dest.is_symlink():
                if _resolved_link_target(dest) != operation.src.resolve():
                    conflicts.append(f"{operation.rel} (destination is a different symlink)")
            elif dest.exists():
                conflicts.append(f"{operation.rel} (overlay destination already exists)")
            continue

        if dest.is_symlink():
            conflicts.append(f"{operation.rel} (destination is a symlink)")
        elif dest.exists() and dest.is_dir():
            conflicts.append(f"{operation.rel} (destination is a directory)")

    if conflicts:
        details = "\n".join(f"- {conflict}" for conflict in sorted(set(conflicts)))
        raise CfgError(
            "Repo apply plan has conflicts in the working tree:\n"
            f"{details}\n\n"
            "Resolve the conflicting paths, then run `cfg repo apply` again."
        )


def build_repo_apply_plan(
    *,
    cfg_root: Path,
    repo_root: Path,
    repo_id: str,
    enabled_owner_ids: Sequence[OwnerId],
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
    previous_state: RepoStateManifest | None = None,
    path_provider_overrides: Mapping[str, str] | None = None,
) -> RepoApplyPlan:
    """Resolve all repo outputs and validate the complete plan without writing."""
    outputs = resolve_repo_outputs(
        cfg_root=cfg_root,
        repo_id=repo_id,
        enabled_owner_ids=enabled_owner_ids,
        manifest_index=manifest_index,
        path_provider_overrides=path_provider_overrides,
    )
    overlays = outputs.overlays
    mirrors = outputs.mirrors
    generated_writes = outputs.generated

    operations: list[RepoOperation] = []
    desired_state: dict[str, ManagedPathState] = {}
    desired_rels = {
        *overlays.desired,
        *mirrors.desired,
        *(write.rel for write in generated_writes),
    }

    for raw_rel, prior in sorted((previous_state or RepoStateManifest()).managed.items()):
        rel = safe_managed_relpath(raw_rel)
        if rel in desired_rels:
            continue
        dest = _safe_destination(repo_root=repo_root, rel=rel)
        if not dest.exists() and not dest.is_symlink():
            continue
        if prior.kind == "overlay":
            if prior.source is None or not Path(prior.source).is_absolute():
                raise CfgError(f"{rel} (stale overlay has no recorded absolute source)")
            operations.append(RemoveOverlay(rel=rel, expected_target=Path(prior.source)))
            continue
        operations.append(
            RemoveManaged(
                owner=prior.owner,
                kind=prior.kind,
                rel=rel,
                expected_digest=prior.digest,
            )
        )

    for rel, owner_file in sorted(overlays.desired.items(), key=lambda item: item[0].as_posix()):
        source = _validate_source(cfg_root=cfg_root, source=owner_file.src, label="Overlay")
        operations.append(LinkOverlay(owner=owner_file.owner, rel=rel, src=source))
        desired_state[rel.as_posix()] = ManagedPathState(
            kind="overlay",
            owner=OwnerId(owner_file.owner),
            digest=_digest_file(source),
            source=str(source),
        )

    for rel, owner_file in sorted(mirrors.desired.items(), key=lambda item: item[0].as_posix()):
        source = _validate_source(cfg_root=cfg_root, source=owner_file.src, label="Mirror")
        content = source.read_bytes()
        operations.append(
            WriteFile(
                owner=owner_file.owner,
                kind="mirror",
                rel=rel,
                content=content,
                mode=stat.S_IMODE(source.stat().st_mode),
                source=str(source),
            )
        )
        desired_state[rel.as_posix()] = ManagedPathState(
            kind="mirror",
            owner=OwnerId(owner_file.owner),
            digest=_digest_bytes(content),
            source=str(source),
        )

    for write in generated_writes:
        if isinstance(write.src, str):
            _validate_source(cfg_root=cfg_root, source=Path(write.src), label="Generated template")
        content = render_template_write_to_string(write).encode("utf-8")
        operations.append(
            WriteFile(
                owner=write.owner,
                kind="generated",
                rel=write.rel,
                content=content,
                mode=0o644,
                source=str(write.src),
            )
        )
        desired_state[write.rel.as_posix()] = ManagedPathState(
            kind="generated",
            owner=write.owner,
            digest=_digest_bytes(content),
            source=str(write.src),
        )

    plan = RepoApplyPlan(
        cfg_root=cfg_root.resolve(),
        repo_root=repo_root.resolve(),
        operations=tuple(operations),
        managed=desired_state,
    )
    _validate_operations(plan)
    return plan


def _write_file(*, dest: Path, content: bytes, mode: int) -> bool:
    current = dest.read_bytes() if dest.is_file() else None
    current_mode = stat.S_IMODE(dest.stat().st_mode) if dest.is_file() else None
    if current == content and current_mode == mode:
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=dest.parent,
            prefix=f".{dest.name}.cfg-",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.chmod(mode)
        temporary_path.replace(dest)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return True


def apply_repo_plan(plan: RepoApplyPlan) -> int:
    """Apply a validated plan and return the number of filesystem changes."""
    _validate_operations(plan)
    changed = 0
    for operation in plan.operations:
        dest = _safe_destination(repo_root=plan.repo_root, rel=operation.rel)
        if isinstance(operation, RemoveOverlay):
            if dest.is_symlink():
                dest.unlink()
                changed += 1
            continue

        if isinstance(operation, RemoveManaged):
            if dest.exists() or dest.is_symlink():
                dest.unlink()
                changed += 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(operation, LinkOverlay):
            if not dest.is_symlink():
                dest.symlink_to(operation.src)
                changed += 1
        elif _write_file(dest=dest, content=operation.content, mode=operation.mode):
            changed += 1
    state = read_repo_state(plan.repo_root)
    state.managed = dict(plan.managed)
    write_repo_state(plan.repo_root, state)
    return changed


def format_repo_plan(plan: RepoApplyPlan) -> list[str]:
    """Format plan operations for dry-run output."""
    lines: list[str] = []
    for operation in plan.operations:
        if isinstance(operation, RemoveOverlay):
            lines.append(f"- remove stale overlay: {operation.rel}")
        elif isinstance(operation, RemoveManaged):
            lines.append(f"- remove stale {operation.kind}: {operation.rel} ({operation.owner})")
        elif isinstance(operation, LinkOverlay):
            lines.append(f"- overlay: {operation.rel} <- {operation.src} ({operation.owner})")
        elif operation.kind == "mirror":
            lines.append(f"- mirror: {operation.rel} <- {operation.source} ({operation.owner})")
        else:
            lines.append(f"- generate: {operation.rel} ({operation.owner})")
    return lines
