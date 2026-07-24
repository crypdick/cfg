from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfg.core.ids import (
    FeatureName,
    HostName,
    OwnerId,
    RepoId,
    parse_feature_name,
    parse_host_name,
    parse_owner_id,
    parse_repo_id,
)
from cfg.core.models import safe_relpath
from cfg.core.scope import Scope

FEATURE_MANIFEST_SCHEMA_VERSION = 1


class FeatureManifest(BaseModel):
    """User-authored metadata stored in a feature directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = FEATURE_MANIFEST_SCHEMA_VERSION
    requires: list[FeatureName] = Field(default_factory=list)
    conflicts: list[FeatureName] = Field(default_factory=list)
    host_requires: list[FeatureName] = Field(default_factory=list)
    generated: list[Path] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema_version_supported(cls, value: int) -> int:
        if int(value) != FEATURE_MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported feature schema_version (expected {FEATURE_MANIFEST_SCHEMA_VERSION})"
            )
        return int(value)

    @field_validator("requires", "conflicts", "host_requires")
    @classmethod
    def _feature_names_short_and_deduped(cls, values: list[str]) -> list[FeatureName]:
        return list(dict.fromkeys(parse_feature_name(value) for value in values))

    @field_validator("generated")
    @classmethod
    def _generated_paths_safe_and_deduped(cls, values: list[str]) -> list[Path]:
        rels = [safe_relpath(str(value).strip()) for value in values if str(value).strip()]
        return list(dict.fromkeys(rels))


@dataclass(frozen=True, slots=True)
class FeatureOwner:
    scope: Scope
    name: FeatureName

    @property
    def id(self) -> OwnerId:
        return OwnerId(f"{self.scope.value}/feature/{self.name}")


@dataclass(frozen=True, slots=True)
class HostOwner:
    name: HostName

    @property
    def id(self) -> OwnerId:
        return OwnerId(f"host/{self.name}")


@dataclass(frozen=True, slots=True)
class RepoOwner:
    repo_id: RepoId

    @property
    def id(self) -> OwnerId:
        return OwnerId(f"repo/{self.repo_id}")


type OwnerRef = FeatureOwner | HostOwner | RepoOwner


def parse_owner_ref(raw: str) -> OwnerRef:
    """Parse an encoded owner id into a scope- and kind-aware owner."""
    parts = parse_owner_id(raw).split("/")
    if len(parts) == 3 and parts[1] == "feature":
        try:
            scope = Scope(parts[0])
        except ValueError as e:
            raise ValueError(f"Invalid owner scope: {raw!r}") from e
        return FeatureOwner(scope=scope, name=parse_feature_name(parts[2]))
    if len(parts) == 2 and parts[0] == Scope.HOST.value:
        return HostOwner(name=parse_host_name(parts[1]))
    if len(parts) == 3 and parts[0] == Scope.REPO.value:
        return RepoOwner(repo_id=parse_repo_id("/".join(parts[1:])))
    raise AssertionError(f"Unhandled parsed owner id: {raw!r}")


def owner_scope(owner_id: OwnerId) -> Scope:
    """Return the already-parsed owner's scope."""
    owner = parse_owner_ref(owner_id)
    if isinstance(owner, FeatureOwner):
        return owner.scope
    if isinstance(owner, HostOwner):
        return Scope.HOST
    return Scope.REPO


@dataclass(frozen=True, slots=True)
class OwnerManifest:
    """Internal owner metadata assembled from parsed boundary values."""

    owner: OwnerRef
    requires: tuple[OwnerId, ...] = ()
    conflicts: tuple[OwnerId, ...] = ()
    generated: tuple[Path, ...] = ()

    @property
    def owner_id(self) -> OwnerId:
        return self.owner.id


def default_owner_manifest(owner_id: OwnerId) -> OwnerManifest:
    """
    Create a default empty manifest for an owner id.
    """
    return OwnerManifest(owner=parse_owner_ref(owner_id))


def owner_id_from_feature_toml_path(*, cfg_root: Path, path: Path) -> OwnerId:
    """
    Derive owner id from a feature owner manifest path:
    - features/host/<name>/feature.toml -> host/feature/<name>
    - features/repo/<name>/feature.toml -> repo/feature/<name>
    """
    from cfg.core.owners.paths import _host_features_root, _repo_features_root

    p = path.resolve()
    roots: list[tuple[str, Path]] = [
        ("host", _host_features_root(cfg_root)),
        ("repo", _repo_features_root(cfg_root)),
    ]
    for scope, root in roots:
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if rel.name != "feature.toml":
            raise ValueError(f"Feature manifest filename must be feature.toml: {path}")
        if len(rel.parts) < 2:
            raise ValueError(f"Feature manifest must be under features/{scope}/<name>/feature.toml: {path}")
        owner_rel = Path(*rel.parts[:-1]).as_posix()
        return FeatureOwner(scope=Scope(scope), name=parse_feature_name(owner_rel)).id
    raise ValueError(f"Feature manifest is not under features/host or features/repo: {path}")
