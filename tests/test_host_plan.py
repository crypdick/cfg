from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cfg.core.errors import CfgError
from cfg.core.models import HostStateManifest, ManagedPathState
from cfg.core.state import read_host_state
from cfg.host.managed_home import HomePlan
from cfg.host.plan import apply_host_cleanup, build_host_apply_plan, capture_host_state
from cfg.owners.fs import OwnerFile
from cfg.render.generated import GeneratedTarget


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_host_state_removes_stale_outputs_and_records_actual_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = tmp_path / "cfg"
    home = tmp_path / "home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    source = cfg_root / "features/host/demo/overlay/current"
    _write(source, "current\n")
    current = home / "current"
    current.parent.mkdir(parents=True)
    current.symlink_to(source)
    stale_source = cfg_root / "features/host/old/overlay/stale"
    stale = home / "stale"
    stale.symlink_to(stale_source)
    generated = home / "generated"
    _write(generated, "generated\n")
    old_generated = home / "old-generated"
    _write(old_generated, "old\n")
    previous = HostStateManifest(
        host="workstation",
        managed={
            "stale": ManagedPathState(
                kind="overlay",
                owner="host/feature/old",
                digest="a" * 64,
                source=str(stale_source),
            ),
            "old-generated": ManagedPathState(
                kind="generated",
                owner="host/feature/old",
                digest=hashlib.sha256(b"old\n").hexdigest(),
            ),
        },
    )
    outputs = HomePlan(
        desired={
            Path("current"): OwnerFile(
                owner="host/feature/demo",
                src=source,
                rel=Path("current"),
            )
        },
        generated={
            Path("generated"): GeneratedTarget(
                owner="host/feature/demo",
                rel=Path("generated"),
            )
        },
    )

    plan = build_host_apply_plan(
        cfg_root=cfg_root,
        home=home,
        host="workstation",
        outputs=outputs,
        previous_state=previous,
    )

    assert apply_host_cleanup(plan) == 2
    assert not stale.exists()
    assert not stale.is_symlink()
    assert not old_generated.exists()
    capture_host_state(plan)
    state = read_host_state()
    assert state.host == "workstation"
    assert {path: item.kind for path, item in state.managed.items()} == {
        "current": "overlay",
        "generated": "generated",
    }


def test_host_plan_preserves_modified_stale_generated_output(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write(home / "changed", "user edit\n")
    previous = HostStateManifest(
        host="workstation",
        managed={
            "changed": ManagedPathState(
                kind="generated",
                owner="host/feature/demo",
                digest="a" * 64,
            )
        },
    )

    with pytest.raises(CfgError, match="changed after cfg last applied"):
        build_host_apply_plan(
            cfg_root=tmp_path / "cfg",
            home=home,
            host="workstation",
            outputs=HomePlan(desired={}, generated={}),
            previous_state=previous,
        )
    assert (home / "changed").read_text(encoding="utf-8") == "user edit\n"


def test_host_plan_replaces_unrecorded_cfg_link_for_generated_output(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfg"
    home = tmp_path / "home"
    old_source = cfg_root / "features/host/old/overlay/settings.json"
    destination = home / ".config/tool/settings.json"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(old_source)
    rel = Path(".config/tool/settings.json")
    outputs = HomePlan(
        desired={},
        generated={rel: GeneratedTarget(owner="host/feature/tool", rel=rel)},
    )

    plan = build_host_apply_plan(
        cfg_root=cfg_root,
        home=home,
        host="workstation",
        outputs=outputs,
        previous_state=HostStateManifest(),
    )

    assert apply_host_cleanup(plan) == 1
    assert not destination.is_symlink()


def test_capture_requires_declared_outputs_to_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    rel = Path("missing")
    plan = build_host_apply_plan(
        cfg_root=tmp_path / "cfg",
        home=home,
        host="workstation",
        outputs=HomePlan(
            desired={},
            generated={rel: GeneratedTarget(owner="host/feature/demo", rel=rel)},
        ),
        previous_state=HostStateManifest(),
    )

    with pytest.raises(CfgError, match="declared generated output is missing"):
        capture_host_state(plan)
    assert not (home / ".config/cfg/state.json").exists()
