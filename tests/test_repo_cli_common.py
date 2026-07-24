from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cfg.core.errors import CfgError
from cfg.core.models import RepoSettings
from cfg.repo import cli_common as cc


@dataclass(frozen=True)
class _FakeStore:
    repo: RepoSettings | None = None
    path: Path = Path("/tmp/repo.toml")

    def get_repo(self, _rid: str) -> RepoSettings | None:
        return self.repo

    def get_repo_path(self, _rid: str) -> Path:
        return self.path


@dataclass(frozen=True)
class _FakeCtx:
    repo_id: str | None
    store: _FakeStore


def test_require_ctx_repo_id_errors_without_repo_id() -> None:
    ctx = _FakeCtx(repo_id=None, store=_FakeStore())
    with pytest.raises(CfgError, match="Could not determine repo id"):
        cc.require_ctx_repo_id(ctx)  # type: ignore[arg-type]


def test_repo_owner_id() -> None:
    assert cc.repo_owner_id("owner/repo") == "repo/owner/repo"


def test_require_registered_repo_errors_and_hint(tmp_path: Path) -> None:
    ctx = _FakeCtx(repo_id="owner/repo", store=_FakeStore(repo=None, path=tmp_path / "x.toml"))
    with pytest.raises(CfgError, match=re.escape("Repo not registered: owner/repo") + "$"):
        cc.require_registered_repo(ctx, "owner/repo")  # type: ignore[arg-type]

    with pytest.raises(CfgError) as e:
        cc.require_registered_repo(ctx, "owner/repo", include_hint=True)  # type: ignore[arg-type]
    assert "Expected:" in str(e.value)


def test_repo_enabled_owner_ids_includes_repo_owner_and_base() -> None:
    cfg = RepoSettings(id="o/r", features=["x"])
    assert cc.repo_enabled_owner_ids(cfg) == ["repo/o/r", "repo/feature/base", "repo/feature/x"]


def test_resolved_repo_owner_ids_plumbs_to_resolver(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = RepoSettings(id="o/r", features=["x"])

    captured: dict[str, Any] = {}

    def fake_resolve_repo_owner_ids(*, cfg_root: Path, enabled_repo_owner_ids: list[str]) -> list[str]:
        captured["cfg_root"] = cfg_root
        captured["enabled"] = list(enabled_repo_owner_ids)
        return ["repo/feature/x", "repo/feature/y"]

    monkeypatch.setattr(cc, "resolve_repo_owner_ids", fake_resolve_repo_owner_ids)

    result = cc.resolved_repo_owner_ids(cfg_root=tmp_path, cfg=cfg)
    assert result == ["repo/feature/x", "repo/feature/y"]
    assert captured["cfg_root"] == tmp_path
    assert captured["enabled"] == ["repo/o/r", "repo/feature/base", "repo/feature/x"]
