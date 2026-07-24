"""Semantic identifiers parsed at cfg's external boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import NewType

RepoId = NewType("RepoId", str)
HostName = NewType("HostName", str)
FeatureName = NewType("FeatureName", str)
OwnerId = NewType("OwnerId", str)


def _single_segment(raw: str, *, label: str) -> str:
    value = str(raw).strip()
    path = Path(value)
    if not value:
        raise ValueError(f"{label} must be non-empty")
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1 or value != path.as_posix():
        raise ValueError(f"{label} must be a single path segment, got: {raw!r}")
    return value


def parse_repo_id(raw: str) -> RepoId:
    """Parse ``owner/repo`` into a repository identifier."""
    value = str(raw).strip()
    path = Path(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or len(path.parts) != 2
        or value != path.as_posix()
    ):
        raise ValueError(f"Repo id must be `owner/repo`, got: {raw!r}")
    return RepoId(value)


def parse_host_name(raw: str) -> HostName:
    """Parse a host name that is safe as one filesystem path segment."""
    return HostName(_single_segment(raw, label="Host name"))


def parse_feature_name(raw: str) -> FeatureName:
    """Parse a scope-local feature name."""
    value = _single_segment(raw, label="Feature name")
    if value.startswith("_"):
        raise ValueError("Feature cannot start with '_' (pyinfra ignores underscore-prefixed groups)")
    return FeatureName(value)


def parse_owner_id(raw: str) -> OwnerId:
    """Parse an encoded host, repo, or feature owner identifier."""
    parts = str(raw).strip().split("/")
    if len(parts) == 3 and parts[0] in {"host", "repo"} and parts[1] == "feature":
        feature = parse_feature_name(parts[2])
        return OwnerId(f"{parts[0]}/feature/{feature}")
    if len(parts) == 2 and parts[0] == "host":
        host = parse_host_name(parts[1])
        return OwnerId(f"host/{host}")
    if len(parts) == 3 and parts[0] == "repo":
        repo_id = parse_repo_id("/".join(parts[1:]))
        return OwnerId(f"repo/{repo_id}")
    raise ValueError(f"Invalid owner id: {raw!r}")
