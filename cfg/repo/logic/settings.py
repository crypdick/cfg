from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from cfg.core.context import CfgContext
from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId
from cfg.core.models import RepoSettings
from cfg.core.owners import OwnerManifest
from cfg.owners.fs import OwnerFile, owner_mirror_files, resolve_owner_files
from cfg.render.generated import resolve_generated_targets
from cfg.render.managed_report import format_managed_sections, generated_sources
from cfg.repo.cli_common import resolved_repo_owner_ids
from cfg.repo.git import git_config_get, git_dir, origin_url, repo_root


def _settings_inventory_report_lines(*, inv_path: Path) -> list[str]:
    inv_path = inv_path.resolve()
    if not inv_path.is_file():
        raise CfgError(f"Repo inventory file not found: {inv_path}")
    inv_contents = inv_path.read_text(encoding="utf-8")
    lines: list[str] = [f"# Contents of {inv_path}"]
    if inv_contents:
        lines.extend(inv_contents.splitlines())
    return lines


def _settings_linked_files(*, repo_root: Path, cfg_root: Path) -> Mapping[Path, object]:
    """
    Scan actual repo symlinks that point into cfg overlay payloads.
    """
    rr = repo_root.resolve()
    owner_roots = (
        ("repo/feature", (cfg_root / "features" / "repo").resolve()),
        ("host/feature", (cfg_root / "features" / "host").resolve()),
        ("repo", (cfg_root / "repos").resolve()),
        ("host", (cfg_root / "hosts").resolve()),
    )

    def _derive_owner_id_from_overlay_target(target: Path) -> str | None:
        tgt = target.resolve()

        for owner_prefix, root in owner_roots:
            try:
                rel = tgt.relative_to(root)
            except ValueError:
                continue
            parts = list(rel.parts)
            if "overlay" not in parts:
                return None
            idx = parts.index("overlay")
            if idx <= 0:
                return None
            rest = Path(*parts[:idx]).as_posix()
            return f"{owner_prefix}/{rest}"
        return None

    linked: dict[Path, OwnerFile] = {}
    for root, dirs, files in os.walk(rr, topdown=True, followlinks=False):
        # prune heavy/irrelevant dirs
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            p = Path(root) / name
            if not p.is_symlink():
                continue
            target = p.resolve()
            owner_id = _derive_owner_id_from_overlay_target(target)
            if not owner_id:
                continue
            try:
                rel_to_repo = p.relative_to(rr)
            except ValueError:
                continue
            linked[rel_to_repo] = OwnerFile(owner=owner_id, src=target, rel=rel_to_repo)
    return linked


def _settings_enabled_owner_ids(
    *,
    cfg_root: Path,
    repo_cfg: RepoSettings,
    manifest_index: Mapping[OwnerId, OwnerManifest],
) -> list[OwnerId]:
    return resolved_repo_owner_ids(
        cfg_root=cfg_root,
        cfg=repo_cfg,
        manifest_index=manifest_index,
    )


def _settings_mirrored_files(
    *,
    cfg_root: Path,
    repo_cfg: RepoSettings,
    manifest_index: Mapping[OwnerId, OwnerManifest],
) -> Mapping[Path, object]:
    enabled_owner_ids = _settings_enabled_owner_ids(
        cfg_root=cfg_root,
        repo_cfg=repo_cfg,
        manifest_index=manifest_index,
    )
    resolved = resolve_owner_files(
        cfg_root=cfg_root,
        enabled_owner_ids=enabled_owner_ids,
        file_getter=lambda cfg, owner_id: owner_mirror_files(cfg_root=cfg, owner_id=owner_id),
        manifest_index=manifest_index,
        path_provider_overrides=(repo_cfg.path_provider_overrides or None),
        conflict_error_prefix="Mirror conflict",
    )
    return resolved.desired


def _settings_generated_files(
    *,
    cfg_root: Path,
    repo_cfg: RepoSettings,
    manifest_index: Mapping[OwnerId, OwnerManifest],
) -> Mapping[Path, object]:
    enabled_owner_ids = _settings_enabled_owner_ids(
        cfg_root=cfg_root,
        repo_cfg=repo_cfg,
        manifest_index=manifest_index,
    )
    gt = resolve_generated_targets(
        cfg_root=cfg_root,
        enabled_owner_ids=enabled_owner_ids,
        manifest_index=manifest_index,
        path_provider_overrides=(repo_cfg.path_provider_overrides or None),
        conflict_error_prefix="Generated artifact conflict",
    )
    return generated_sources(cfg_root=cfg_root, desired_targets=gt.desired)


def settings() -> list[str]:
    """Business logic for `cfg repo settings` (returns lines to print)."""
    rr = repo_root()
    url = origin_url(rr)

    ctx = CfgContext.load()
    rid = ctx.repo_id

    hooks_path = git_config_get(rr, "core.hooksPath")
    hook_file = git_dir(rr) / "hooks" / "pre-commit"

    exclude_file = git_dir(rr) / "info" / "exclude"
    exclude_text = exclude_file.read_text(encoding="utf-8") if exclude_file.is_file() else ""
    has_cfg_ignore = ".cfg/" in exclude_text or ".cfg\n" in exclude_text
    has_cursor_ignore = ".cursor/" in exclude_text or ".cursor\n" in exclude_text
    has_envrc_ignore = ".envrc" in exclude_text

    from cfg.core.state import read_repo_state

    state = read_repo_state(rr)

    lines: list[str] = []
    lines.append(f"repo_root: {rr}")
    lines.append(f"origin:    {url or '(missing)'}")
    lines.append(f"repo_id:   {rid or '(unknown)'}")
    lines.append("")

    lines.append("attachment:")
    lines.append(f"  core.hooksPath: {hooks_path or '(unset)'}")
    lines.append(f"  hook_file:      {hook_file}  (exists={hook_file.exists()})")
    lines.append(f"  exclude_file:   {exclude_file}")
    lines.append(
        f"  ignores:        .cfg={has_cfg_ignore}  .cursor={has_cursor_ignore}  .envrc={has_envrc_ignore}"
    )
    lines.append(f"  state:          prev_core_hooks_path={state.attach.prev_core_hooks_path!r} (legacy)")
    lines.append("")

    if not rid:
        lines.append("inventory: (no repo id; cannot look up repo cfg.toml)")
        return lines

    cfg = ctx.store.get_repo(rid)
    if cfg is None:
        lines.append("inventory: (not registered)")
        lines.append(f"hint: run `cfg repo init` to register {rid} in the personalization inventory")
        return lines

    inv_path = ctx.store.get_repo_path(rid)
    lines.extend(_settings_inventory_report_lines(inv_path=inv_path))
    lines.append("---")
    lines.append("# Detailed list of specific files being managed")
    lines.append("")

    snapshot = ctx.snapshot
    linked = _settings_linked_files(repo_root=rr, cfg_root=ctx.root)
    mirrored = _settings_mirrored_files(
        cfg_root=ctx.root,
        repo_cfg=cfg,
        manifest_index=snapshot.manifest_index,
    )
    generated = _settings_generated_files(
        cfg_root=ctx.root,
        repo_cfg=cfg,
        manifest_index=snapshot.manifest_index,
    )

    lines.extend(format_managed_sections(linked=linked, mirrored=mirrored, generated=generated))
    return lines
