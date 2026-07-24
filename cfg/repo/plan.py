"""Plan and apply repo-managed files without an orchestration layer."""

from __future__ import annotations

import filecmp
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.models import safe_relpath
from cfg.owners.fs import OwnerFile, owner_overlay_files, resolve_owner_files
from cfg.render.generated import (
    render_repo_generated_template_writes,
    render_template_write_to_string,
)
from cfg.repo.publish import resolve_repo_publish_files


@dataclass(frozen=True)
class RemoveOverlay:
    rel: Path


@dataclass(frozen=True)
class LinkOverlay:
    owner: str
    rel: Path
    src: Path


@dataclass(frozen=True)
class CopyMirror:
    owner: str
    rel: Path
    src: Path


@dataclass(frozen=True)
class WriteGenerated:
    owner: str
    rel: Path
    content: str


RepoOperation = RemoveOverlay | LinkOverlay | CopyMirror | WriteGenerated


@dataclass(frozen=True)
class RepoApplyPlan:
    """A complete, validated set of repo filesystem operations."""

    cfg_root: Path
    repo_root: Path
    operations: tuple[RepoOperation, ...]


def _overlay_file_getter(
    cfg_root: Path,
    owner_id: str,
) -> list[OwnerFile]:
    return owner_overlay_files(cfg_root=cfg_root, owner_id=owner_id)


def _safe_destination(*, repo_root: Path, rel: Path) -> Path:
    try:
        normalized = safe_relpath(rel.as_posix())
    except ValueError as e:
        raise CfgError(f"Unsafe managed repo path: {rel}") from e
    if normalized == Path("."):
        raise CfgError("Refusing to manage the repo root itself.")
    return repo_root / normalized


def _resolved_link_target(path: Path) -> Path:
    target = Path(os.readlink(path))
    if not target.is_absolute():
        target = path.parent / target
    return target.resolve(strict=False)


def _is_cfg_owned_overlay(*, path: Path, cfg_root: Path) -> bool:
    if not path.is_symlink():
        return False
    target = _resolved_link_target(path)
    for root in (cfg_root / "features" / "repo", cfg_root / "repos"):
        try:
            rel = target.relative_to(root.resolve())
        except ValueError:
            continue
        if "overlay" in rel.parts:
            return True
    return False


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
            if parent == Path("."):
                break
            if parent in rels:
                conflicts.append(
                    f"{rel} ({desired[rel]} destination is nested below "
                    f"{desired[parent]} destination {parent})"
                )
                break


def _validate_operations(plan: RepoApplyPlan) -> None:
    conflicts: list[str] = []
    for operation in plan.operations:
        dest = _safe_destination(repo_root=plan.repo_root, rel=operation.rel)
        _validate_parent_path(repo_root=plan.repo_root, rel=operation.rel, conflicts=conflicts)

        if isinstance(operation, RemoveOverlay):
            if dest.is_symlink() and not _is_cfg_owned_overlay(path=dest, cfg_root=plan.cfg_root):
                conflicts.append(f"{operation.rel} (stale symlink is no longer cfg-owned)")
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
    enabled_owner_ids: list[str],
    path_provider_overrides: dict[str, str] | None = None,
) -> RepoApplyPlan:
    """Resolve all repo outputs and validate the complete plan without writing."""
    overrides = dict(path_provider_overrides or {})
    overlays = resolve_owner_files(
        cfg_root=cfg_root,
        enabled_owner_ids=enabled_owner_ids,
        file_getter=_overlay_file_getter,
        path_provider_overrides=overrides,
        conflict_error_prefix="Overlay conflict",
    )
    mirrors = resolve_repo_publish_files(
        cfg_root=cfg_root,
        enabled_owner_ids=enabled_owner_ids,
        path_provider_overrides=overrides,
    )
    generated_writes = render_repo_generated_template_writes(
        cfg_root=cfg_root,
        repo_id=repo_id,
        enabled_owner_ids=enabled_owner_ids,
        path_provider_overrides=overrides,
    )

    desired_kinds: dict[Path, str] = {}
    cross_mode_conflicts: list[str] = []
    for kind, rels in (
        ("overlay", overlays.desired),
        ("mirror", mirrors.desired),
        ("generated", {write.rel: write for write in generated_writes}),
    ):
        for rel in rels:
            previous = desired_kinds.get(rel)
            if previous is not None:
                cross_mode_conflicts.append(f"{rel} ({previous} vs {kind})")
            else:
                desired_kinds[rel] = kind
    _validate_no_nested_destinations(desired_kinds, cross_mode_conflicts)
    if cross_mode_conflicts:
        details = "\n".join(f"- {conflict}" for conflict in sorted(set(cross_mode_conflicts)))
        raise CfgError(f"Repo output conflict detected:\n{details}")

    operations: list[RepoOperation] = []
    for rel in sorted(overlays.all_known_rels - overlays.desired.keys(), key=lambda path: path.as_posix()):
        dest = _safe_destination(repo_root=repo_root, rel=rel)
        if _is_cfg_owned_overlay(path=dest, cfg_root=cfg_root):
            operations.append(RemoveOverlay(rel=rel))

    for rel, owner_file in sorted(overlays.desired.items(), key=lambda item: item[0].as_posix()):
        source = _validate_source(cfg_root=cfg_root, source=owner_file.src, label="Overlay")
        operations.append(LinkOverlay(owner=owner_file.owner, rel=rel, src=source))

    for rel, owner_file in sorted(mirrors.desired.items(), key=lambda item: item[0].as_posix()):
        source = _validate_source(cfg_root=cfg_root, source=owner_file.src, label="Mirror")
        operations.append(CopyMirror(owner=owner_file.owner, rel=rel, src=source))

    for write in generated_writes:
        if isinstance(write.src, str):
            _validate_source(cfg_root=cfg_root, source=Path(write.src), label="Generated template")
        operations.append(
            WriteGenerated(
                owner=write.owner,
                rel=write.rel,
                content=render_template_write_to_string(write),
            )
        )

    plan = RepoApplyPlan(
        cfg_root=cfg_root.resolve(),
        repo_root=repo_root.resolve(),
        operations=tuple(operations),
    )
    _validate_operations(plan)
    return plan


def _write_generated(*, dest: Path, content: str) -> bool:
    current = dest.read_text(encoding="utf-8") if dest.is_file() else None
    current_mode = stat.S_IMODE(dest.stat().st_mode) if dest.is_file() else None
    if current == content and current_mode == 0o644:
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=dest.parent,
            prefix=f".{dest.name}.cfg-",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.chmod(0o644)
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

        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(operation, LinkOverlay):
            if not dest.is_symlink():
                dest.symlink_to(operation.src)
                changed += 1
        elif isinstance(operation, CopyMirror):
            if not dest.is_file() or not filecmp.cmp(operation.src, dest, shallow=False):
                shutil.copy2(operation.src, dest)
                changed += 1
        elif _write_generated(dest=dest, content=operation.content):
            changed += 1
    return changed


def format_repo_plan(plan: RepoApplyPlan) -> list[str]:
    """Format plan operations for dry-run output."""
    lines: list[str] = []
    for operation in plan.operations:
        if isinstance(operation, RemoveOverlay):
            lines.append(f"- remove stale overlay: {operation.rel}")
        elif isinstance(operation, LinkOverlay):
            lines.append(f"- overlay: {operation.rel} <- {operation.src} ({operation.owner})")
        elif isinstance(operation, CopyMirror):
            lines.append(f"- mirror: {operation.rel} <- {operation.src} ({operation.owner})")
        else:
            lines.append(f"- generate: {operation.rel} ({operation.owner})")
    return lines
