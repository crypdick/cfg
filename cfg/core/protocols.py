from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cfg.core.models import HostSettings, RepoSettings, SshSettings


@runtime_checkable
class HostSettingsLike(Protocol):
    # Mirrors the subset of HostSettings consumed by runtime inventory generation.
    name: str
    features: list[str]
    repos: dict[str, Path]
    vars: dict[str, Any]
    ssh: SshSettings | None


@runtime_checkable
class HostStoreLike(Protocol):
    """Subset of the inventory store consumed by host CLI helpers."""

    def get_host(self, host_name: str) -> HostSettings | None: ...
    def get_host_path(self, host_name: str) -> Path: ...


@runtime_checkable
class RepoStoreLike(Protocol):
    """Subset of the inventory store consumed by repo CLI helpers."""

    def get_repo(self, repo_id: str) -> RepoSettings | None: ...
    def get_repo_path(self, repo_id: str) -> Path: ...


@runtime_checkable
class HostCtxLike(Protocol):
    """Subset of `CfgContext` consumed by host CLI helpers.

    Only side-effect-free members are listed: `host_name`/`repo_id` on the real
    context are lazy properties, and naming them here would force resolution
    during beartype's structural isinstance check.
    """

    @property
    def store(self) -> HostStoreLike: ...


@runtime_checkable
class RepoCtxLike(Protocol):
    """Subset of `CfgContext` consumed by repo CLI helpers."""

    @property
    def repo_id(self) -> str | None: ...

    @property
    def store(self) -> RepoStoreLike: ...
