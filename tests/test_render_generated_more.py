from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from cfg.core.errors import CfgError
from cfg.render.generated import (
    TemplateWrite,
    collect_template_fragments,
    render_repo_generated_template_writes,
    render_template_write_to_string,
    resolve_generated_targets,
)


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _owner_manifest(_owner_id: str, *, generated: list[str]) -> str:
    gen = ", ".join(f'"{g}"' for g in generated)
    return f"""
schema_version = 1
requires = []
conflicts = []
generated = [{gen}]
""".lstrip()


def test_resolve_generated_targets_conflict_without_override(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        _owner_manifest("repo/feature/a", generated=["x.txt"]),
    )
    _write(
        cfg_root / "features" / "repo" / "b" / "feature.toml",
        _owner_manifest("repo/feature/b", generated=["x.txt"]),
    )

    with pytest.raises(CfgError, match="Generated artifact conflict"):
        resolve_generated_targets(cfg_root=cfg_root, enabled_owner_ids=["repo/feature/a", "repo/feature/b"])


def test_resolve_generated_targets_override_selects_provider(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        _owner_manifest("repo/feature/a", generated=["x.txt"]),
    )
    _write(
        cfg_root / "features" / "repo" / "b" / "feature.toml",
        _owner_manifest("repo/feature/b", generated=["x.txt"]),
    )

    resolved = resolve_generated_targets(
        cfg_root=cfg_root,
        enabled_owner_ids=["repo/feature/a", "repo/feature/b"],
        path_provider_overrides={"x.txt": "repo/feature/b"},
    )
    assert resolved.desired[Path("x.txt")].owner == "repo/feature/b"


def test_collect_template_fragments_groups_by_dir_and_stem(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    owner_id = "repo/feature/a"
    rel = Path(".pre-commit-config.yaml")
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        _owner_manifest(owner_id, generated=[rel.as_posix()]),
    )

    # Two fragment styles:
    # - grouped by first directory segment
    _write(
        cfg_root / "features" / "repo" / "a" / "render" / "fragments" / rel.as_posix() / "repos" / "00_a.yml",
        "a\n",
    )
    # - grouped by stem when at root
    _write(
        cfg_root / "features" / "repo" / "a" / "render" / "fragments" / rel.as_posix() / "exclude.txt",
        "x\n",
    )

    fragments, fragment_files = collect_template_fragments(
        cfg_root=cfg_root, enabled_owner_ids=[owner_id], rel=rel
    )
    assert "repos" in fragments
    assert "exclude" in fragments
    assert len(fragment_files) == 2


def test_render_repo_generated_template_writes_smoke(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    owner_id = "repo/feature/a"
    rel = Path("x.txt")
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        _owner_manifest(owner_id, generated=[rel.as_posix()]),
    )
    _write(
        cfg_root / "features" / "repo" / "a" / "render" / "templates" / "x.txt.j2",
        "hello {{ _cfg.repo_id }}\n",
    )

    writes = render_repo_generated_template_writes(
        cfg_root=cfg_root,
        repo_id="owner/repo",
        enabled_owner_ids=[owner_id],
    )
    assert len(writes) == 1
    assert writes[0].owner == owner_id
    assert writes[0].rel == rel

    rendered = render_template_write_to_string(writes[0])
    assert rendered == "hello owner/repo\n"


def test_render_template_write_to_string_supports_stringio() -> None:
    w = TemplateWrite(
        owner="x",
        rel=Path("x"),
        src=StringIO("hi {{name}}"),
        data={"name": "you"},
        jinja_env_kwargs={},
    )
    assert render_template_write_to_string(w) == "hi you"
