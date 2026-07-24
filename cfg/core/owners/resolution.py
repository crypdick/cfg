from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.inventory import Inventory
from cfg.core.models import HostSettings
from cfg.core.owners.manifest_io import load_owner_manifest_index
from cfg.core.owners.models import OwnerManifest
from cfg.core.scope import Scope


def _normalize_enabled(enabled: list[str]) -> tuple[list[str], dict[str, int]]:
    enabled = list(dict.fromkeys([str(o).strip() for o in enabled if str(o).strip()]))
    enabled_pos: dict[str, int] = {o: i for i, o in enumerate(enabled)}
    return enabled, enabled_pos


def _require_known(manifest_index: dict[str, OwnerManifest], owner_id: str) -> OwnerManifest:
    if owner_id not in manifest_index:
        # Provide a clearer error message explaining "owner" terminology.
        hint = ""
        if owner_id.startswith("host/feature/"):
            short_name = owner_id.replace("host/feature/", "")
            hint = (
                f"\n\nThe feature '{short_name}' is not defined in the cfg inventory.\n"
                f"Fix options:\n"
                f"  - Remove it: cfg host feature remove {short_name}\n"
                f"  - Create it: cfg host feature create {short_name}"
            )
        elif owner_id.startswith("repo/feature/"):
            short_name = owner_id.replace("repo/feature/", "")
            hint = (
                f"\n\nThe feature '{short_name}' is not defined in the cfg inventory.\n"
                f"Fix options:\n"
                f"  - Remove it: cfg repo feature remove {short_name}\n"
                f"  - Create it: cfg repo feature create {short_name}"
            )
        raise CfgError(f"Feature not found: {owner_id}{hint}")
    return manifest_index[owner_id]


def _expand_closure(
    *,
    enabled: list[str],
    manifest_index: dict[str, OwnerManifest],
    dep_allowed: Callable[[str], bool],
) -> set[str]:
    closure: set[str] = set()
    stack: list[str] = list(enabled)
    while stack:
        oid = stack.pop()
        if oid in closure:
            continue
        meta = _require_known(manifest_index, oid)
        closure.add(oid)
        stack.extend(dep for dep in meta.deps.requires if dep_allowed(dep))
    return closure


def _raise_on_conflicts(*, closure: set[str], manifest_index: dict[str, OwnerManifest]) -> None:
    conflicts: set[str] = set()
    for oid in sorted(closure):
        meta = _require_known(manifest_index, oid)
        for c in meta.deps.conflicts:
            if c in closure:
                conflicts.add(" vs ".join(sorted([oid, c])))
    if conflicts:
        msg = "\n".join(f"- {p}" for p in sorted(conflicts))
        raise CfgError(f"Owner conflict detected:\n{msg}")


def _toposort_owners(
    *,
    closure: set[str],
    manifest_index: dict[str, OwnerManifest],
    enabled_pos: dict[str, int],
    dep_allowed: Callable[[str], bool],
) -> list[str]:
    import heapq

    deps_by_owner: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = {o: set() for o in closure}
    in_degree: dict[str, int] = dict.fromkeys(closure, 0)

    for oid in closure:
        meta = _require_known(manifest_index, oid)
        deps = {d for d in meta.deps.requires if d in closure and dep_allowed(d)}
        deps_by_owner[oid] = deps
        in_degree[oid] = len(deps)
        for d in deps:
            dependents[d].add(oid)

    out: list[str] = []
    ready: list[tuple[int, str]] = [
        (enabled_pos.get(o, 10**9), o) for o, deg in in_degree.items() if deg == 0
    ]
    heapq.heapify(ready)

    while ready:
        _pos, oid = heapq.heappop(ready)
        out.append(oid)
        for dep in dependents[oid]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                heapq.heappush(ready, (enabled_pos.get(dep, 10**9), dep))

    if len(out) != len(closure):
        remaining = sorted([o for o in closure if o not in set(out)])
        msg = "\n".join(f"- {o} requires {sorted(deps_by_owner.get(o, set()))}" for o in remaining)
        raise CfgError(f"Owner dependency cycle detected:\n{msg}")

    return out


def resolve_owners(*, enabled: list[str], manifest_index: dict[str, OwnerManifest]) -> list[str]:
    """
    Resolve a list of enabled owners into a dependency-closed, conflict-free,
    deterministically ordered list.

    Ordering:
    - deps before dependents
    - among ready nodes: enabled-list order, then name
    """
    # Unscoped resolution == scoped resolution that follows every dependency edge.
    return resolve_owners_scoped(enabled=enabled, manifest_index=manifest_index, allowed_prefixes=None)


def resolve_owners_scoped(
    *,
    enabled: list[str],
    manifest_index: dict[str, OwnerManifest],
    allowed_prefixes: tuple[str, ...] | None,
) -> list[str]:
    """
    Resolve owners like `resolve_owners`, but only follows dependency edges where the
    dependency owner id starts with one of `allowed_prefixes`.

    This is important for cross-scope deps like:
    - repo owners requiring host owners (host install deps)
    Without scoping, repo workflows could accidentally include host owners and try
    to apply home-scoped paths into a repo working tree.
    """

    enabled, enabled_pos = _normalize_enabled(enabled)

    def dep_allowed(owner_id: str) -> bool:
        if allowed_prefixes is None:
            return True
        return any(str(owner_id).startswith(p) for p in allowed_prefixes)

    closure = _expand_closure(enabled=enabled, manifest_index=manifest_index, dep_allowed=dep_allowed)
    _raise_on_conflicts(closure=closure, manifest_index=manifest_index)
    return _toposort_owners(
        closure=closure, manifest_index=manifest_index, enabled_pos=enabled_pos, dep_allowed=dep_allowed
    )


def resolve_repo_owner_ids(*, cfg_root: Path, enabled_repo_owner_ids: list[str]) -> list[str]:
    """
    Resolve repo owner ids, expanding repo-scoped dependencies only.
    """
    idx = load_owner_manifest_index(cfg_root)
    return resolve_owners_scoped(
        enabled=enabled_repo_owner_ids, manifest_index=idx, allowed_prefixes=("repo/",)
    )


def resolve_host_owner_ids_implied_by_repo(*, cfg_root: Path, enabled_repo_owner_ids: list[str]) -> list[str]:
    """
    Compute host-scoped owner ids implied by a set of repo-scoped owner ids.

    This is used by repo workflows that need to validate/ensure host prerequisites
    (e.g. `repo/feature/uv` -> `host/feature/uv`) while keeping host mutations
    explicit/opt-in.
    """
    idx = load_owner_manifest_index(cfg_root)
    resolved_all = resolve_owners_scoped(
        enabled=enabled_repo_owner_ids,
        manifest_index=idx,
        allowed_prefixes=("host/", "repo/"),
    )
    return [oid for oid in resolved_all if str(oid).startswith("host/")]


def resolve_host_owner_ids_for_host(
    *,
    cfg_root: Path,
    cfg_inventory: Inventory,
    host_settings: HostSettings,
) -> list[str]:
    """
    Compute host-effective owner ids for host-scoped deploys.

    Seeds:
    - implicit `host/<name>` owner id
    - plus scope-local feature names from host settings
    - plus repo owners configured for repos attached to the host (implicit `repo/<id>` + repo feature ids)

    Then closes over dependencies (including cross-scope deps), but returns ONLY host/* owners
    so host/home deploys don't accidentally try to apply repo-scoped overlay paths into $HOME.
    """

    # Semantics (2026-01): "features" are enabled owner ids.
    #
    # - Hosts always enable `host/<name>`
    # - Hosts always enable the base host feature (`host/feature/base`) implicitly
    enabled: list[str] = [
        f"host/{host_settings.name}",
        Scope.HOST.base_feature_id,
        *(Scope.HOST.feature_id(feature) for feature in host_settings.features),
    ]

    # Add repo owners (in deterministic order).
    repos_map = dict(host_settings.repos or {})
    for repo_id in sorted(repos_map.keys()):
        loaded = getattr(cfg_inventory, "repos", {}).get(repo_id)
        if loaded is None:
            raise CfgError(
                f"Host {host_settings.name!r} references repo {repo_id!r} but it is not registered in cfg inventory."
            )
        # Repo owners are also derived from inventory: repo/<id> + repo base + repo features.
        enabled.append(f"repo/{loaded.settings.id}")
        enabled.append(Scope.REPO.base_feature_id)
        enabled.extend(Scope.REPO.feature_id(feature) for feature in loaded.settings.features)

    idx = load_owner_manifest_index(cfg_root)
    resolved_all = resolve_owners_scoped(
        enabled=enabled,
        manifest_index=idx,
        allowed_prefixes=("host/", "repo/"),
    )
    return [oid for oid in resolved_all if str(oid).startswith("host/")]
