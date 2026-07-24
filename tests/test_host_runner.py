from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cfg.core.errors import CfgError
from cfg.core.inventory import Inventory, Loaded
from cfg.core.models import HostSettings
from cfg.host import runner as hr

if TYPE_CHECKING:
    from pathlib import Path


def test_resolve_targets_errors_on_empty_selector() -> None:
    inv = Inventory(repos={}, hosts={})
    with pytest.raises(CfgError, match="Missing --hosts selector"):
        hr.resolve_targets(inv, "   ")


def test_resolve_targets_by_name_group_list_and_dedupe(tmp_path: Path) -> None:
    h1 = HostSettings(name="h1", features=["desktop", "x"])
    h2 = HostSettings(name="h2", features=["server", "desktop"])
    inv = Inventory(
        repos={},
        hosts={
            "h1": Loaded(settings=h1, source_path=tmp_path / "h1.toml"),
            "h2": Loaded(settings=h2, source_path=tmp_path / "h2.toml"),
        },
    )

    assert hr.resolve_targets(inv, "h1") == ["h1"]
    assert hr.resolve_targets(inv, "desktop") == ["h1", "h2"]
    assert hr.resolve_targets(inv, "desktop,h1,desktop,@local") == ["h1", "h2", "@local"]

    with pytest.raises(CfgError, match="Unknown host/group selector"):
        hr.resolve_targets(inv, "nope")


def test_get_inventory_path_prefers_static(tmp_path: Path) -> None:
    cfg_root = tmp_path
    inv = Inventory(repos={}, hosts={})
    static = cfg_root / "inventory.py"
    static.write_text("# x\n", encoding="utf-8")

    inv_path, tmpdir = hr._get_inventory_path(cfg_root, inv, current_host_for_local=None, limit=["h1"])
    assert inv_path == static
    assert tmpdir is None


def test_get_inventory_path_generates_runtime_inventory_and_local_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = tmp_path
    inv = Inventory(repos={}, hosts={})

    calls: list[bool] = []

    def fake_write_runtime_inventory(**kw: Any) -> tuple[Path, Path]:
        calls.append(bool(kw["include_local"]))
        inv_path = cfg_root / "tmp" / "inventory.py"
        tmpdir = cfg_root / "tmp"
        inv_path.parent.mkdir(parents=True, exist_ok=True)
        inv_path.write_text("# gen\n", encoding="utf-8")
        return inv_path, tmpdir

    monkeypatch.setattr(hr, "write_runtime_inventory", fake_write_runtime_inventory)

    inv_path, tmpdir = hr._get_inventory_path(cfg_root, inv, current_host_for_local="h1", limit=["h1"])
    assert inv_path.is_file()
    assert tmpdir is not None
    assert calls[-1] is False

    inv_path2, tmpdir2 = hr._get_inventory_path(cfg_root, inv, current_host_for_local="h1", limit=["@local"])
    assert inv_path2.is_file()
    assert tmpdir2 is not None
    assert calls[-1] is True


def test_run_pyinfra_merges_env_and_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = tmp_path
    inv = Inventory(repos={}, hosts={})
    deploy = cfg_root / "deploy.py"
    deploy.write_text("# d\n", encoding="utf-8")

    inv_path = cfg_root / "tmp" / "inventory.py"
    tmpdir = cfg_root / "tmp"
    inv_path.parent.mkdir(parents=True, exist_ok=True)
    inv_path.write_text("# inv\n", encoding="utf-8")

    monkeypatch.setattr(hr, "_get_inventory_path", lambda *_a, **_k: (inv_path, tmpdir))

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(hr, "_run_pyinfra", lambda **kw: calls.append(kw))

    cleaned: list[Path] = []
    monkeypatch.setattr(hr, "cleanup_runtime_inventory", cleaned.append)

    hr.run_pyinfra(
        cfg_root=cfg_root,
        cfg_inventory=inv,
        limit=["h1"],
        deploy_file=deploy,
        current_host_for_local="h1",
        extra_env={"X": "1"},
    )

    assert calls, "expected _run_pyinfra call"
    kw = calls[-1]
    assert kw["cwd"] == cfg_root
    assert kw["inventory_path"] == inv_path
    assert kw["operations"] == [str(deploy)]
    assert kw["limit"] == ["h1"]
    assert kw["extra_env"]["CFG_ROOT"] == str(cfg_root)
    assert kw["extra_env"]["CFG_HOST_FOR_LOCAL"] == "h1"
    assert kw["extra_env"]["X"] == "1"

    assert cleaned == [tmpdir]


def test_run_pyinfra_debug_inventory_uses_debug_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = tmp_path
    inv = Inventory(repos={}, hosts={})

    inv_path = cfg_root / "tmp" / "inventory.py"
    tmpdir = cfg_root / "tmp"
    inv_path.parent.mkdir(parents=True, exist_ok=True)
    inv_path.write_text("# inv\n", encoding="utf-8")

    monkeypatch.setattr(hr, "_get_inventory_path", lambda *_a, **_k: (inv_path, tmpdir))

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(hr, "_run_pyinfra", lambda **kw: calls.append(kw))
    monkeypatch.setattr(hr, "cleanup_runtime_inventory", lambda _p: None)

    hr.run_pyinfra_debug_inventory(
        cfg_root=cfg_root,
        cfg_inventory=inv,
        limit=None,
        current_host_for_local=None,
        extra_env=None,
    )
    assert calls[-1]["operations"] == ["debug-inventory"]
