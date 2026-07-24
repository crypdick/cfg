from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from cfg.core.ids import FeatureName, HostName, RepoId
from cfg.core.models import HostSettings, RepoSettings, SshSettings


class HostSettingsLike(Protocol):
    # Mirrors the subset of HostSettings consumed by runtime inventory generation.
    @property
    def name(self) -> HostName: ...

    @property
    def features(self) -> Sequence[FeatureName]: ...

    @property
    def repos(self) -> Mapping[RepoId, Path]: ...

    @property
    def vars(self) -> Mapping[str, Any]: ...

    @property
    def ssh(self) -> SshSettings | None: ...


class HostStoreLike(Protocol):
    """Subset of the inventory store consumed by host CLI helpers."""

    def get_host(self, host_name: str) -> HostSettings | None: ...
    def get_host_path(self, host_name: str) -> Path: ...


class RepoStoreLike(Protocol):
    """Subset of the inventory store consumed by repo CLI helpers."""

    def get_repo(self, repo_id: str) -> RepoSettings | None: ...
    def get_repo_path(self, repo_id: str) -> Path: ...


class HostCtxLike(Protocol):
    """Subset of `CfgContext` consumed by host CLI helpers.

    Only the capability consumed by host helpers is part of this contract.
    """

    @property
    def store(self) -> HostStoreLike: ...


class RepoCtxLike(Protocol):
    """Subset of `CfgContext` consumed by repo CLI helpers."""

    @property
    def repo_id(self) -> RepoId | None: ...

    @property
    def store(self) -> RepoStoreLike: ...
