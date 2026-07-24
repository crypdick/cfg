from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId, parse_owner_id
from cfg.core.inventory import Inventory
from cfg.core.owners.manifest_io import load_owner_manifest_index
from cfg.core.owners.models import OwnerManifest, owner_scope
from cfg.core.protocols import HostSettingsLike
from cfg.core.scope import Scope


def _parse_enabled(enabled: Sequence[str]) -> tuple[list[OwnerId], dict[OwnerId, int]]:
    parsed = list(dict.fromkeys(parse_owner_id(owner_id) for owner_id in enabled))
    enabled_pos = {owner_id: position for position, owner_id in enumerate(parsed)}
    return parsed, enabled_pos


def _require_known(
    manifest_index: Mapping[OwnerId, OwnerManifest],
    owner_id: OwnerId,
) -> OwnerManifest:
    if owner_id not in manifest_index:
        # Provide a clearer error message explaining "owner" terminology.
        hint = ""
        if owner_id.startswith(Scope.HOST.feature_prefix):
            short_name = owner_id.removeprefix(Scope.HOST.feature_prefix)
            hint = (
                f"\n\nThe feature '{short_name}' is not defined in the cfg inventory.\n"
                f"Fix options:\n"
                f"  - Remove it: cfg host feature remove {short_name}\n"
                f"  - Create it: cfg host feature create {short_name}"
            )
        elif owner_id.startswith(Scope.REPO.feature_prefix):
            short_name = owner_id.removeprefix(Scope.REPO.feature_prefix)
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
    enabled: list[OwnerId],
    manifest_index: Mapping[OwnerId, OwnerManifest],
    dep_allowed: Callable[[OwnerId], bool],
) -> set[OwnerId]:
    closure: set[OwnerId] = set()
    stack = list(enabled)
    while stack:
        owner_id = stack.pop()
        if owner_id in closure:
            continue
        manifest = _require_known(manifest_index, owner_id)
        closure.add(owner_id)
        stack.extend(dependency for dependency in manifest.requires if dep_allowed(dependency))
    return closure


def _raise_on_conflicts(
    *,
    closure: set[OwnerId],
    manifest_index: Mapping[OwnerId, OwnerManifest],
) -> None:
    conflicts: set[str] = set()
    for owner_id in sorted(closure):
        manifest = _require_known(manifest_index, owner_id)
        for conflict in manifest.conflicts:
            if conflict in closure:
                conflicts.add(" vs ".join(sorted([owner_id, conflict])))
    if conflicts:
        msg = "\n".join(f"- {p}" for p in sorted(conflicts))
        raise CfgError(f"Owner conflict detected:\n{msg}")


def _toposort_owners(
    *,
    closure: set[OwnerId],
    manifest_index: Mapping[OwnerId, OwnerManifest],
    enabled_pos: dict[OwnerId, int],
    dep_allowed: Callable[[OwnerId], bool],
) -> list[OwnerId]:
    import heapq

    deps_by_owner: dict[OwnerId, set[OwnerId]] = {}
    dependents: dict[OwnerId, set[OwnerId]] = {owner_id: set() for owner_id in closure}
    in_degree: dict[OwnerId, int] = dict.fromkeys(closure, 0)

    for owner_id in closure:
        manifest = _require_known(manifest_index, owner_id)
        dependencies = {
            dependency
            for dependency in manifest.requires
            if dependency in closure and dep_allowed(dependency)
        }
        deps_by_owner[owner_id] = dependencies
        in_degree[owner_id] = len(dependencies)
        for dependency in dependencies:
            dependents[dependency].add(owner_id)

    out: list[OwnerId] = []
    ready: list[tuple[int, OwnerId]] = [
        (enabled_pos.get(owner_id, 10**9), owner_id) for owner_id, degree in in_degree.items() if degree == 0
    ]
    heapq.heapify(ready)

    while ready:
        _position, owner_id = heapq.heappop(ready)
        out.append(owner_id)
        for dependent in dependents[owner_id]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                heapq.heappush(ready, (enabled_pos.get(dependent, 10**9), dependent))

    if len(out) != len(closure):
        remaining = sorted(owner_id for owner_id in closure if owner_id not in set(out))
        msg = "\n".join(
            f"- {owner_id} requires {sorted(deps_by_owner.get(owner_id, set()))}" for owner_id in remaining
        )
        raise CfgError(f"Owner dependency cycle detected:\n{msg}")

    return out


def resolve_owners(
    *,
    enabled: Sequence[str],
    manifest_index: Mapping[OwnerId, OwnerManifest],
) -> list[OwnerId]:
    """
    Resolve a list of enabled owners into a dependency-closed, conflict-free,
    deterministically ordered list.

    Ordering:
    - deps before dependents
    - among ready nodes: enabled-list order, then name
    """
    # Unscoped resolution == scoped resolution that follows every dependency edge.
    return resolve_owners_scoped(enabled=enabled, manifest_index=manifest_index, allowed_scopes=None)


def resolve_owners_scoped(
    *,
    enabled: Sequence[str],
    manifest_index: Mapping[OwnerId, OwnerManifest],
    allowed_scopes: frozenset[Scope] | None,
) -> list[OwnerId]:
    """
    Resolve owners like `resolve_owners`, but only follows dependency edges where the
    the dependency belongs to one of `allowed_scopes`.

    This is important for cross-scope deps like:
    - repo owners requiring host owners (host install deps)
    Without scoping, repo workflows could accidentally include host owners and try
    to apply home-scoped paths into a repo working tree.
    """

    parsed_enabled, enabled_pos = _parse_enabled(enabled)

    def dep_allowed(owner_id: OwnerId) -> bool:
        if allowed_scopes is None:
            return True
        return owner_scope(owner_id) in allowed_scopes

    closure = _expand_closure(
        enabled=parsed_enabled,
        manifest_index=manifest_index,
        dep_allowed=dep_allowed,
    )
    _raise_on_conflicts(closure=closure, manifest_index=manifest_index)
    return _toposort_owners(
        closure=closure, manifest_index=manifest_index, enabled_pos=enabled_pos, dep_allowed=dep_allowed
    )


def resolve_repo_owner_ids(
    *,
    cfg_root: Path,
    enabled_repo_owner_ids: Sequence[str],
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
) -> list[OwnerId]:
    """
    Resolve repo owner ids, expanding repo-scoped dependencies only.
    """
    idx = manifest_index if manifest_index is not None else load_owner_manifest_index(cfg_root)
    return resolve_owners_scoped(
        enabled=enabled_repo_owner_ids,
        manifest_index=idx,
        allowed_scopes=frozenset({Scope.REPO}),
    )


def resolve_host_owner_ids_implied_by_repo(
    *,
    cfg_root: Path,
    enabled_repo_owner_ids: Sequence[str],
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
) -> list[OwnerId]:
    """
    Compute host-scoped owner ids implied by a set of repo-scoped owner ids.

    This supports read-only validation and reporting for declarations such as
    `repo/feature/uv` -> `host/feature/uv`; it never mutates a host.
    """
    idx = manifest_index if manifest_index is not None else load_owner_manifest_index(cfg_root)
    resolved_all = resolve_owners_scoped(
        enabled=enabled_repo_owner_ids,
        manifest_index=idx,
        allowed_scopes=frozenset(Scope),
    )
    return [owner_id for owner_id in resolved_all if owner_scope(owner_id) is Scope.HOST]


def resolve_host_owner_ids_for_host(
    *,
    cfg_root: Path,
    cfg_inventory: Inventory,
    host_settings: HostSettingsLike,
    manifest_index: Mapping[OwnerId, OwnerManifest] | None = None,
) -> list[OwnerId]:
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
        str(parse_owner_id(f"host/{host_settings.name}")),
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
        enabled.append(str(parse_owner_id(f"repo/{loaded.settings.id}")))
        enabled.append(str(Scope.REPO.base_feature_id))
        enabled.extend(str(Scope.REPO.feature_id(feature)) for feature in loaded.settings.features)

    idx = (
        manifest_index
        if manifest_index is not None
        else load_owner_manifest_index(cfg_root, inventory=cfg_inventory)
    )
    resolved_all = resolve_owners_scoped(
        enabled=enabled,
        manifest_index=idx,
        allowed_scopes=frozenset(Scope),
    )
    return [owner_id for owner_id in resolved_all if owner_scope(owner_id) is Scope.HOST]
