from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfg.core.models import safe_relpath

FEATURE_MANIFEST_SCHEMA_VERSION = 1


def _short_feature_name(raw: str) -> str:
    name = str(raw).strip()
    path = safe_relpath(name)
    if not name or len(path.parts) != 1:
        raise ValueError(f"Feature names must be a single short name, got: {raw!r}")
    return name


class FeatureManifest(BaseModel):
    """User-authored metadata stored in a feature directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = FEATURE_MANIFEST_SCHEMA_VERSION
    requires: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    host_requires: list[str] = Field(default_factory=list)
    generated: list[str] = Field(default_factory=list)

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
    def _feature_names_short_and_deduped(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_short_feature_name(value) for value in values))

    @field_validator("generated")
    @classmethod
    def _generated_paths_safe_and_deduped(cls, values: list[str]) -> list[str]:
        rels = [safe_relpath(str(value).strip()).as_posix() for value in values if str(value).strip()]
        return list(dict.fromkeys(rels))


class OwnerDeps(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requires: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)

    @field_validator("requires", "conflicts")
    @classmethod
    def _normalize_owner_ids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in list(v or []):
            oid = str(raw).strip()
            if not oid:
                continue
            safe_relpath(oid)
            out.append(oid)
        # de-dup preserving order
        return list(dict.fromkeys(out))


class OwnerInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str

    @field_validator("id")
    @classmethod
    def _id_safe(cls, v: str) -> str:
        oid = str(v).strip()
        if not oid:
            raise ValueError("owner.id must be non-empty")
        safe_relpath(oid)
        return oid


class OwnerManifest(BaseModel):
    """Internal resolved feature metadata keyed by a scoped owner id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: OwnerInfo
    deps: OwnerDeps = Field(default_factory=OwnerDeps)
    generated: list[str] = Field(default_factory=list)

    @field_validator("generated")
    @classmethod
    def _generated_paths_safe_and_deduped(cls, values: list[str]) -> list[str]:
        rels = [safe_relpath(str(value).strip()).as_posix() for value in values if str(value).strip()]
        return list(dict.fromkeys(rels))


def default_owner_manifest(owner_id: str) -> OwnerManifest:
    """
    Create a default empty manifest for an owner id.
    """
    return OwnerManifest(
        owner=OwnerInfo(id=owner_id),
        deps=OwnerDeps(requires=[], conflicts=[]),
        generated=[],
    )


def owner_id_from_feature_toml_path(*, cfg_root: Path, path: Path) -> str:
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
        return f"{scope}/feature/{owner_rel}"
    raise ValueError(f"Feature manifest is not under features/host or features/repo: {path}")
