from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.models import HostSettings
from cfg.host import cli_common as cc

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class _FakeStore:
    hosts: dict[str, HostSettings]
    root: Path

    def get_host(self, host: str) -> HostSettings | None:
        return self.hosts.get(host)

    def get_host_path(self, host: str) -> Path:
        # Mirrors the real store path shape closely enough for hint text.
        return self.root / "hosts" / host / "cfg.toml"


@dataclass(frozen=True)
class _FakeCtx:
    root: Path
    host_name: str
    store: _FakeStore


def _write(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_host_ctx_defaults_to_ctx_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from cfg.core.store import InventoryStore

    # `_host_name` is preset so the lazy property short-circuits the host-file read.
    ctx_obj = cc.CfgContext(root=tmp_path, store=InventoryStore(tmp_path), _host_name="h1")
    monkeypatch.setattr(cc.CfgContext, "load", lambda: ctx_obj)

    ctx, host = cc.host_ctx(None)
    assert ctx is ctx_obj
    assert host == "h1"

    _ctx2, host2 = cc.host_ctx("explicit")
    assert host2 == "explicit"


def test_require_registered_host_success(tmp_path: Path) -> None:
    hs = HostSettings(name="h1", features=["desktop"])
    store = _FakeStore(hosts={"h1": hs}, root=tmp_path)
    ctx = _FakeCtx(root=tmp_path, host_name="h1", store=store)

    out = cc.require_registered_host(ctx, "h1")
    assert out == hs


def test_require_registered_host_error_and_hint(tmp_path: Path) -> None:
    store = _FakeStore(hosts={}, root=tmp_path)
    ctx = _FakeCtx(root=tmp_path, host_name="h1", store=store)

    with pytest.raises(CfgError, match="Host not registered: h2"):
        cc.require_registered_host(ctx, "h2")

    with pytest.raises(CfgError, match="Expected:") as e:
        cc.require_registered_host(ctx, "h2", include_hint=True)
    msg = str(e.value)
    assert "Expected:" in msg
    assert "Fix: cfg host init h2" in msg


def test_resolve_workflow_path_path_mode(tmp_path: Path) -> None:
    cfg_root = tmp_path

    with pytest.raises(CfgError, match="cannot be empty"):
        cc.resolve_workflow_path(cfg_root, "  ")

    # Relative path is resolved under cfg_root.
    _write(cfg_root / "x" / "wf.py", "x")
    p = cc.resolve_workflow_path(cfg_root, "x/wf.py")
    assert p == (cfg_root / "x" / "wf.py").resolve()

    # Absolute path is accepted as-is (but must exist).
    abs_p = cfg_root / "abs.py"
    _write(abs_p, "x")
    p2 = cc.resolve_workflow_path(cfg_root, str(abs_p))
    assert p2 == abs_p.resolve()

    with pytest.raises(CfgError, match="Workflow file missing"):
        cc.resolve_workflow_path(cfg_root, "missing/wf.py")


def test_resolve_workflow_path_name_mode(tmp_path: Path) -> None:
    cfg_root = tmp_path

    p = cc.resolve_workflow_path(cfg_root, "apply_home")
    assert p == cc.builtin_workflow_path("apply_home")
    assert p.is_file()

    with pytest.raises(CfgError, match="Unknown workflow: nope"):
        cc.resolve_workflow_path(cfg_root, "nope")
