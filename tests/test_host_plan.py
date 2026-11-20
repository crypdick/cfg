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


@pytest.mark.parametrize("prior_kind", ["generated", "overlay"])
@pytest.mark.parametrize("matches_desired", [True, False])
def test_host_plan_resumes_completed_overlay_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior_kind: str, *, matches_desired: bool
) -> None:
    cfg_root = tmp_path / "cfg"
    home = tmp_path / "home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    rel = Path("settings.json")
    source = cfg_root / "features/host/new/overlay" / rel
    _write(source, "new settings\n")
    home.mkdir()
    destination = home / rel
    destination.symlink_to(source if matches_desired else tmp_path / "user-settings.json")
    outputs = HomePlan(
        desired={rel: OwnerFile(owner="host/feature/new", src=source, rel=rel)},
        generated={},
    )
    previous = HostStateManifest(
        host="workstation",
        managed={
            rel.as_posix(): ManagedPathState(
                kind=prior_kind,
                owner="host/feature/old",
                digest="a" * 64,
                source=str(cfg_root / "features/host/old/overlay" / rel) if prior_kind == "overlay" else None,
            ),
        },
    )
    if not matches_desired:
        with pytest.raises(CfgError, match="Host apply plan has conflicts"):
            build_host_apply_plan(
                cfg_root=cfg_root, home=home, host="workstation", outputs=outputs, previous_state=previous
            )
        assert destination.readlink() == tmp_path / "user-settings.json"
        return

    plan = build_host_apply_plan(
        cfg_root=cfg_root, home=home, host="workstation", outputs=outputs, previous_state=previous
    )
    assert apply_host_cleanup(plan) == 0
    assert destination.readlink() == source
    capture_host_state(plan)
    recorded = read_host_state().managed[rel.as_posix()]
    assert recorded.kind == "overlay"
    assert recorded.owner == "host/feature/new"
    assert recorded.source == str(source)


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


def test_capture_explains_dangling_generated_output_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    rel = Path(".claude/settings.json")
    destination = home / rel
    destination.parent.mkdir(parents=True)
    destination.symlink_to(tmp_path / "retired-generated-settings.json")
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

    with pytest.raises(CfgError) as error:
        capture_host_state(plan)

    message = str(error.value)
    assert "dangling symlink" in message
    assert "retired-generated-settings.json" in message
    assert "remove the stale symlink and rerun `cfg host apply`" in message
    assert not (home / ".config/cfg/state.json").exists()
