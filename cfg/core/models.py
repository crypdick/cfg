"""
Pydantic models for cfg.

This module defines:
- Inventory models (`RepoSettings`, `HostSettings`)
- Safety helpers for repo ids and relative paths (repo ids are used as directories)
- Repo-local state manifest models (`RepoStateManifest`) stored in `.cfg/state.json`

Key invariant:
- A repo id is treated like a *relative path* (e.g. `owner/repo`), and
  is validated to be safe for path usage (no absolute paths, no `..`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def dedupe_preserve_order(items: list[str]) -> list[str]:
    """Dedupe a list of strings while preserving order. Strips and skips empty values."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        v = str(raw).strip()
        if not v:
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def safe_relpath(raw: str) -> Path:
    """
    Validate a user-provided relative path (no absolute paths, no `..`).
    Returns the normalized Path instance.
    """
    p = Path(raw)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Unsafe relative path: {raw!r}")
    return p


def safe_repo_id_path(repo_id: str) -> Path:
    """
    Convert a normalized repo id like `owner/repo` into a safe Path for
    repo-specific storage inside the personalization repository.
    """
    p = safe_relpath(repo_id)
    if len(p.parts) != 2:
        raise ValueError(f"Repo id must be `owner/repo`, got: {repo_id!r}")
    return p


def _validate_feature_list(features: list[str]) -> list[str]:
    out = dedupe_preserve_order(list(features))
    for feature in out:
        path = safe_relpath(feature)
        if len(path.parts) != 1:
            raise ValueError(f"Use a short feature name without a scope prefix: {feature!r}")
        if feature == "base":
            raise ValueError("Do not configure base explicitly; it is always enabled implicitly.")
    return out


class RepoSettings(BaseModel):
    """
    Repo inventory entry stored in the personalization repository.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    # Optional origin remote URL (used for cloning/syncing and validation).
    # Example: "git@github.com:owner/repo.git"  # noqa: ERA001
    origin_url: str | None = None
    alias: str | None = None
    # Scope-local short feature names.
    features: list[str] = Field(default_factory=list)

    # Explicit resolution for overlay path conflicts:
    # relpath (posix-like) -> feature name that should provide it.
    path_provider_overrides: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id_normalized_and_safe(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("Repo id must be non-empty")
        # Only validate it's safe for path usage; identity normalization is handled elsewhere.
        safe_repo_id_path(v)
        return v

    @field_validator("origin_url")
    @classmethod
    def _origin_url_strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @field_validator("features")
    @classmethod
    def _features_dedupe(cls, v: list[str]) -> list[str]:
        return _validate_feature_list(v)

    @field_validator("path_provider_overrides")
    @classmethod
    def _provider_overrides_safe(cls, v: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, provider in (v or {}).items():
            rel = safe_relpath(str(k))
            prov = str(provider).strip()
            if not prov:
                raise ValueError(f"Empty provider for override path: {k!r}")
            out[str(rel)] = prov
        return out


class SshSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str | None = None
    user: str | None = None
    port: int | None = 22


class HostSettings(BaseModel):
    """
    Host inventory entry stored in the personalization repository.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    # Scope-local short feature names.
    features: list[str] = Field(default_factory=list)
    ssh: SshSettings | None = None

    # Repo checkouts on this machine: repo_id -> local path
    repos: dict[str, Path] = Field(default_factory=dict)

    # Free-form vars for templating/pyinfra, etc.
    vars: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _host_name_nonempty(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("Host name must be non-empty")
        return v

    @field_validator("features")
    @classmethod
    def _features_dedupe(cls, v: list[str]) -> list[str]:
        return _validate_feature_list(v)

    @field_validator("repos")
    @classmethod
    def _repos_keys_safe(cls, v: dict[str, Path]) -> dict[str, Path]:
        out: dict[str, Path] = {}
        for repo_id, path in (v or {}).items():
            rid = str(repo_id).strip()
            if not rid:
                raise ValueError("Repo id key must be non-empty")
            safe_repo_id_path(rid)
            out[rid] = Path(path)
        return out


class RepoAttachState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Retained state for restoring core.hooksPath values stored in repo manifests.
    # Attach leaves core.hooksPath unset because custom values break hook installation.
    prev_core_hooks_path: str | None = None

    # Patterns added to .git/info/exclude by cfg attach.
    exclude_patterns_added: list[str] = Field(default_factory=list)


class RepoStateManifest(BaseModel):
    """
    Stored in target repos at `.cfg/state.json`.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    attach: RepoAttachState = Field(default_factory=RepoAttachState)
