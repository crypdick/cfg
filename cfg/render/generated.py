"""
Generalized "generated artifacts" engine.

Repo feature manifests can declare generated outputs via:

    generated = ["<dest-relpath>", ...]

This module resolves generated outputs across enabled owners (with conflict handling)
and turns them into renderable template-write descriptions.

Today implemented artifacts:
- template: render an owner-provided Jinja2 template file into the destination (optionally
  with raw text fragments collected from enabled owners).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId
from cfg.core.owners import OwnerManifest, load_owner_manifest_index, owner_id_to_dir
from cfg.owners.providers import select_path_providers


@dataclass(frozen=True)
class GeneratedTarget:
    owner: OwnerId
    rel: Path  # destination relpath within the repository


@dataclass(frozen=True)
class ResolvedGeneratedTargets:
    desired: dict[Path, GeneratedTarget]  # rel -> chosen target provider


@dataclass(frozen=True)
class TemplateWrite:
    """
    A single template-write description.

    - src is either a filesystem path (string) or an IO object (StringIO).
    - rel is repository-relative.
    """

    owner: OwnerId
    rel: Path
    src: str | StringIO
    data: dict[str, Any]
    jinja_env_kwargs: dict[str, Any]


DEFAULT_JINJA_ENV_KWARGS: dict[str, Any] = {
    # These defaults make templates much nicer for YAML-like outputs.
    "trim_blocks": True,
    "lstrip_blocks": True,
}


def _generated_from_manifest(
    *,
    owner_id: OwnerId,
    manifest: OwnerManifest,
) -> list[GeneratedTarget]:
    return [GeneratedTarget(owner=owner_id, rel=Path(str(path))) for path in manifest.generated]


def resolve_generated_targets(
    *,
    cfg_root: Path,
    enabled_owner_ids: Sequence[OwnerId],
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
    path_provider_overrides: Mapping[str, str] | None = None,
    conflict_error_prefix: str = "Generated artifact conflict",
) -> ResolvedGeneratedTargets:
    """
    Resolve generated outputs declared by enabled owners, with conflict detection.

    Conflicts:
    - Two enabled owners declaring the same destination relpath is an error unless
      `path_provider_overrides` selects a provider owner id for that relpath.
    """
    path_provider_overrides = dict(path_provider_overrides or {})
    if manifest_index is None:
        manifest_index = load_owner_manifest_index(cfg_root)

    providers: dict[Path, list[GeneratedTarget]] = {}
    for owner_id in enabled_owner_ids or []:
        manifest = manifest_index.get(owner_id)
        if manifest is None:
            raise CfgError(f"Unknown owner (not in manifest index): {owner_id}")
        for gt in _generated_from_manifest(owner_id=owner_id, manifest=manifest):
            providers.setdefault(gt.rel, []).append(gt)

    desired = select_path_providers(
        providers,
        path_provider_overrides=path_provider_overrides,
        conflict_error_prefix=conflict_error_prefix,
    )

    return ResolvedGeneratedTargets(desired=desired)


def _template_src_path_for_owner(
    *,
    cfg_root: Path,
    owner_id: OwnerId,
    rel: Path,
) -> Path:
    """
    Convention for generated templates:
    - destination rel: <rel>
    - template source: <owner-dir>/render/templates/<rel>.j2
    """
    owner_dir = owner_id_to_dir(cfg_root, owner_id)
    return owner_dir / "render" / "templates" / f"{rel.as_posix()}.j2"


def _template_fragment_root_for_owner(
    *,
    cfg_root: Path,
    owner_id: OwnerId,
    rel: Path,
) -> Path:
    """
    Convention for template fragments for a generated output:
    - destination rel: <rel>
    - fragment root: <owner-dir>/render/fragments/<rel>/
      (contains any text files; the template decides how to interpret them)
    """
    owner_dir = owner_id_to_dir(cfg_root, owner_id)
    return owner_dir / "render" / "fragments" / rel.as_posix()


def _rel_to_cfg_root(*, cfg_root: Path, path: Path) -> str:
    cfg_root = cfg_root.resolve()
    try:
        return path.resolve().relative_to(cfg_root).as_posix()
    except ValueError:
        return path.as_posix()


def collect_template_fragments(
    *,
    cfg_root: Path,
    enabled_owner_ids: Sequence[OwnerId],
    rel: Path,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """
    Collect raw text fragments for a given generated output relpath across enabled owners.

    Returns:
    - fragments: dict[group -> list[fragment dicts]]
    - fragment_files: flat list of fragment dicts (same dict objects)

    Grouping convention:
    - If fragment file path under the fragment root has at least 2 path segments, group is
      the first segment (e.g. `repos/00.yml` -> group `repos`).
    - If it's a single file at the root, group is its stem (e.g. `exclude.txt` -> group `exclude`).
    """
    fragments: dict[str, list[dict[str, Any]]] = {}
    fragment_files: list[dict[str, Any]] = []

    for owner_id in list(enabled_owner_ids or []):
        root = _template_fragment_root_for_owner(cfg_root=cfg_root, owner_id=owner_id, rel=rel)
        if not root.is_dir():
            continue

        for p in sorted([pp for pp in root.rglob("*") if pp.is_file()]):
            try:
                content = p.read_text(encoding="utf-8")
            except OSError as e:
                raise CfgError(f"Failed to read template fragment: {p}\n{e}") from e

            name = p.relative_to(root).as_posix()
            parts = Path(name).parts
            group = str(parts[0]) if len(parts) >= 2 else Path(name).stem

            frag: dict[str, Any] = {
                "owner": owner_id,
                "name": name,
                "group": group,
                "content": content,
                "abs_path": str(p),
                "rel_to_cfg_root": _rel_to_cfg_root(cfg_root=cfg_root, path=p),
            }
            fragments.setdefault(group, []).append(frag)
            fragment_files.append(frag)

    return fragments, fragment_files


def render_template_write_to_string(w: TemplateWrite) -> str:
    """
    Render a `TemplateWrite` into a final string using Jinja2 (no YAML-aware logic).
    """
    env_kwargs = dict(w.jinja_env_kwargs or {})
    # Preserve trailing newlines unless explicitly overridden.
    env_kwargs.setdefault("keep_trailing_newline", True)
    if isinstance(w.src, StringIO):
        env = Environment(**env_kwargs)  # noqa: S701 -- generating non-HTML config files, autoescape would corrupt output
        return env.from_string(w.src.getvalue()).render(**(w.data or {}))

    src_path = Path(str(w.src))
    env = Environment(loader=FileSystemLoader(str(src_path.parent)), **env_kwargs)  # noqa: S701 -- generating non-HTML config files, autoescape would corrupt output
    tmpl = env.get_template(src_path.name)
    return tmpl.render(**(w.data or {}))


def render_repo_generated_template_writes(
    *,
    cfg_root: Path,
    repo_id: str,
    enabled_owner_ids: Sequence[OwnerId],
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
    path_provider_overrides: Mapping[str, str] | None = None,
    only_rels: set[Path] | None = None,
) -> list[TemplateWrite]:
    """
    Resolve repo-generated artifacts into renderable template writes.
    """
    resolved = resolve_generated_targets(
        cfg_root=cfg_root,
        enabled_owner_ids=enabled_owner_ids,
        manifest_index=manifest_index,
        path_provider_overrides=path_provider_overrides,
        conflict_error_prefix="Generated artifact conflict",
    )

    writes: list[TemplateWrite] = []
    for rel, gt in sorted(resolved.desired.items(), key=lambda kv: kv[0].as_posix()):
        if only_rels is not None and rel not in only_rels:
            continue

        src_path = _template_src_path_for_owner(cfg_root=cfg_root, owner_id=gt.owner, rel=rel)
        if not src_path.is_file():
            raise CfgError(
                "Missing generated template source:\n"
                f"- owner: {gt.owner}\n"
                f"- rel: {rel.as_posix()}\n"
                f"- expected_template: {src_path}\n"
            )
        fragments, fragment_files = collect_template_fragments(
            cfg_root=cfg_root, enabled_owner_ids=enabled_owner_ids, rel=rel
        )
        writes.append(
            TemplateWrite(
                owner=gt.owner,
                rel=rel,
                src=str(src_path),
                data={
                    "_cfg": {
                        "root": str(cfg_root),
                        "repo_id": str(repo_id),
                        "owner_id": str(gt.owner),
                        "rel": rel.as_posix(),
                    },
                    "fragments": fragments,
                    "fragment_files": fragment_files,
                },
                jinja_env_kwargs=dict(DEFAULT_JINJA_ENV_KWARGS),
            )
        )

    return writes
