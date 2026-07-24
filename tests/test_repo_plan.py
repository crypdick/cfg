from __future__ import annotations

from pathlib import Path

import pytest

from cfg.core.errors import CfgError
from cfg.core.models import ManagedPathState, RepoStateManifest
from cfg.core.state import read_repo_state
from cfg.repo.plan import (
    LinkOverlay,
    RemoveManaged,
    RemoveOverlay,
    apply_repo_plan,
    build_repo_apply_plan,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _owner_manifest(
    _owner_id: str,
    *,
    overlay: list[str] | None = None,
    mirror: list[str] | None = None,
    generated: list[str] | None = None,
) -> str:
    del overlay, mirror

    def values(items: list[str] | None) -> str:
        return ", ".join(f'"{item}"' for item in items or [])

    return f"""
schema_version = 1
requires = []
conflicts = []
generated = [{values(generated)}]
""".lstrip()


def _feature_root(cfg_root: Path, name: str) -> Path:
    return cfg_root / "features" / "repo" / name


def test_plan_applies_all_modes_and_is_idempotent(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    owner_root = _feature_root(cfg_root, "demo")
    _write(
        owner_root / "feature.toml",
        _owner_manifest(
            "repo/feature/demo",
            overlay=["linked.txt"],
            mirror=["copied.txt"],
            generated=["rendered.txt"],
        ),
    )
    _write(owner_root / "overlay" / "linked.txt", "linked\n")
    _write(owner_root / "mirror" / "copied.txt", "copied\n")
    _write(owner_root / "render" / "templates" / "rendered.txt.j2", "hello {{ _cfg.repo_id }}\n")

    plan = build_repo_apply_plan(
        cfg_root=cfg_root,
        repo_root=repo_root,
        repo_id="owner/repo",
        enabled_owner_ids=["repo/feature/demo"],
    )

    assert apply_repo_plan(plan) == 3
    assert (repo_root / "linked.txt").is_symlink()
    assert (repo_root / "linked.txt").resolve() == (owner_root / "overlay" / "linked.txt").resolve()
    assert (repo_root / "copied.txt").read_text(encoding="utf-8") == "copied\n"
    assert (repo_root / "rendered.txt").read_text(encoding="utf-8") == "hello owner/repo\n"
    state = read_repo_state(repo_root)
    assert {rel: item.kind for rel, item in state.managed.items()} == {
        "copied.txt": "mirror",
        "linked.txt": "overlay",
        "rendered.txt": "generated",
    }

    second_plan = build_repo_apply_plan(
        cfg_root=cfg_root,
        repo_root=repo_root,
        repo_id="owner/repo",
        enabled_owner_ids=["repo/feature/demo"],
        previous_state=state,
    )
    assert apply_repo_plan(second_plan) == 0

    prune_plan = build_repo_apply_plan(
        cfg_root=cfg_root,
        repo_root=repo_root,
        repo_id="owner/repo",
        enabled_owner_ids=[],
        previous_state=read_repo_state(repo_root),
    )
    assert {operation.rel for operation in prune_plan.operations} == {
        Path("linked.txt"),
        Path("copied.txt"),
        Path("rendered.txt"),
    }
    assert sum(isinstance(operation, RemoveManaged) for operation in prune_plan.operations) == 2
    assert apply_repo_plan(prune_plan) == 3
    assert not (repo_root / "linked.txt").exists()
    assert not (repo_root / "copied.txt").exists()
    assert not (repo_root / "rendered.txt").exists()
    assert read_repo_state(repo_root).managed == {}


@pytest.mark.parametrize("rel", ["linked.txt", "copied.txt", "rendered.txt"])
def test_plan_refuses_to_prune_user_modified_managed_output(tmp_path: Path, rel: str) -> None:
    cfg_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    owner_root = _feature_root(cfg_root, "demo")
    _write(
        owner_root / "feature.toml",
        _owner_manifest(
            "repo/feature/demo",
            overlay=["linked.txt"],
            mirror=["copied.txt"],
            generated=["rendered.txt"],
        ),
    )
    _write(owner_root / "overlay" / "linked.txt", "linked\n")
    _write(owner_root / "mirror" / "copied.txt", "copied\n")
    _write(owner_root / "render" / "templates" / "rendered.txt.j2", "rendered\n")
    initial_plan = build_repo_apply_plan(
        cfg_root=cfg_root,
        repo_root=repo_root,
        repo_id="owner/repo",
        enabled_owner_ids=["repo/feature/demo"],
    )
    apply_repo_plan(initial_plan)
    state = read_repo_state(repo_root)

    target = repo_root / rel
    if target.is_symlink():
        target.unlink()
    _write(target, "user edit\n")

    with pytest.raises(CfgError, match="stale"):
        build_repo_apply_plan(
            cfg_root=cfg_root,
            repo_root=repo_root,
            repo_id="owner/repo",
            enabled_owner_ids=[],
            previous_state=state,
        )
    assert target.read_text(encoding="utf-8") == "user edit\n"


def test_plan_forgets_stale_state_when_output_is_already_absent(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    previous_state = RepoStateManifest(
        managed={
            "gone.txt": ManagedPathState(
                kind="mirror",
                owner="repo/feature/demo",
                digest="a" * 64,
            )
        }
    )

    plan = build_repo_apply_plan(
        cfg_root=cfg_root,
        repo_root=repo_root,
        repo_id="owner/repo",
        enabled_owner_ids=[],
        previous_state=previous_state,
    )

    assert plan.operations == ()
    assert apply_repo_plan(plan) == 0
    assert read_repo_state(repo_root).managed == {}


def test_plan_reports_all_worktree_conflicts_before_writing(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    owner_root = _feature_root(cfg_root, "demo")
    _write(
        owner_root / "feature.toml",
        _owner_manifest(
            "repo/feature/demo",
            overlay=["linked.txt"],
            generated=["rendered.txt"],
        ),
    )
    _write(owner_root / "overlay" / "linked.txt", "linked\n")
    _write(owner_root / "render" / "templates" / "rendered.txt.j2", "rendered\n")
    _write(repo_root / "linked.txt", "user file\n")
    (repo_root / "rendered.txt").mkdir()

    with pytest.raises(CfgError) as exc_info:
        build_repo_apply_plan(
            cfg_root=cfg_root,
            repo_root=repo_root,
            repo_id="owner/repo",
            enabled_owner_ids=["repo/feature/demo"],
        )

    message = str(exc_info.value)
    assert "linked.txt (overlay destination already exists)" in message
    assert "rendered.txt (destination is a directory)" in message
    assert (repo_root / "linked.txt").read_text(encoding="utf-8") == "user file\n"


def test_plan_rejects_cross_mode_and_nested_outputs(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    first = _feature_root(cfg_root, "first")
    second = _feature_root(cfg_root, "second")
    _write(first / "feature.toml", _owner_manifest("repo/feature/first", overlay=["shared"]))
    _write(first / "overlay" / "shared", "overlay\n")
    _write(
        second / "feature.toml",
        _owner_manifest("repo/feature/second", mirror=["shared", "parent/child"]),
    )
    _write(second / "mirror" / "shared", "mirror\n")
    _write(second / "mirror" / "parent" / "child", "child\n")

    with pytest.raises(CfgError, match="overlay vs mirror"):
        build_repo_apply_plan(
            cfg_root=cfg_root,
            repo_root=repo_root,
            repo_id="owner/repo",
            enabled_owner_ids=["repo/feature/first", "repo/feature/second"],
        )

    _write(first / "feature.toml", _owner_manifest("repo/feature/first", overlay=["parent"]))
    _write(first / "overlay" / "parent", "parent\n")
    with pytest.raises(CfgError, match="nested below"):
        build_repo_apply_plan(
            cfg_root=cfg_root,
            repo_root=repo_root,
            repo_id="owner/repo",
            enabled_owner_ids=["repo/feature/first", "repo/feature/second"],
        )


def test_plan_removes_only_stale_cfg_owned_overlay(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    owner_root = _feature_root(cfg_root, "old")
    _write(owner_root / "feature.toml", _owner_manifest("repo/feature/old", overlay=["old.txt"]))
    _write(owner_root / "overlay" / "old.txt", "old\n")
    (repo_root / "old.txt").symlink_to(owner_root / "overlay" / "old.txt")
    outside = tmp_path / "outside.txt"
    _write(outside, "outside\n")
    (repo_root / "external.txt").symlink_to(outside)

    plan = build_repo_apply_plan(
        cfg_root=cfg_root,
        repo_root=repo_root,
        repo_id="owner/repo",
        enabled_owner_ids=[],
    )

    assert plan.operations == (RemoveOverlay(rel=Path("old.txt")),)
    assert apply_repo_plan(plan) == 1
    assert not (repo_root / "old.txt").exists()
    assert (repo_root / "external.txt").is_symlink()


def test_plan_refuses_parent_symlink_escape(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    owner_root = _feature_root(cfg_root, "demo")
    _write(
        owner_root / "feature.toml",
        _owner_manifest("repo/feature/demo", mirror=["nested/file.txt"]),
    )
    _write(owner_root / "mirror" / "nested" / "file.txt", "managed\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo_root / "nested").symlink_to(outside, target_is_directory=True)

    with pytest.raises(CfgError, match="parent path is a symlink"):
        build_repo_apply_plan(
            cfg_root=cfg_root,
            repo_root=repo_root,
            repo_id="owner/repo",
            enabled_owner_ids=["repo/feature/demo"],
        )
    assert not (outside / "file.txt").exists()


def test_plan_represents_overlay_sources_explicitly(tmp_path: Path) -> None:
    cfg_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    owner_root = _feature_root(cfg_root, "demo")
    _write(owner_root / "feature.toml", _owner_manifest("repo/feature/demo", overlay=["x.txt"]))
    _write(owner_root / "overlay" / "x.txt", "x\n")

    plan = build_repo_apply_plan(
        cfg_root=cfg_root,
        repo_root=repo_root,
        repo_id="owner/repo",
        enabled_owner_ids=["repo/feature/demo"],
    )

    assert plan.operations == (
        LinkOverlay(
            owner="repo/feature/demo",
            rel=Path("x.txt"),
            src=(owner_root / "overlay" / "x.txt").resolve(),
        ),
    )
