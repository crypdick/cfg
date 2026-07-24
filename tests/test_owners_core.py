from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.owners import load_owner_manifest_index, resolve_owners
from cfg.owners.fs import owner_overlay_files

if TYPE_CHECKING:
    from pathlib import Path


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_load_owner_manifest_index_derives_id_from_path_and_validates_match(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(
        cfg_root / "features" / "repo" / "uv" / "feature.toml",
        """
schema_version = 1
requires = []
host_requires = ["uv"]
conflicts = []
generated = []
""".lstrip(),
    )

    idx = load_owner_manifest_index(cfg_root)
    assert set(idx.keys()) == {"repo/feature/uv"}
    assert idx["repo/feature/uv"].requires == ("host/feature/uv",)


def test_resolve_owners_expands_requires_and_orders_deps_first(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(
        cfg_root / "features" / "host" / "uv" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "repo" / "uv" / "feature.toml",
        """
schema_version = 1
requires = []
host_requires = ["uv"]
conflicts = []
generated = []
""".lstrip(),
    )

    idx = load_owner_manifest_index(cfg_root)
    resolved = resolve_owners(enabled=["repo/feature/uv"], manifest_index=idx)
    assert resolved == ["host/feature/uv", "repo/feature/uv"]


def test_resolve_owners_detects_conflicts(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = ["b"]
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "repo" / "b" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )

    idx = load_owner_manifest_index(cfg_root)
    with pytest.raises(CfgError, match="Owner conflict"):
        resolve_owners(enabled=["repo/feature/a", "repo/feature/b"], manifest_index=idx)


def test_feature_manifest_rejects_legacy_payload_lists(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(
        cfg_root / "features" / "repo" / "dup" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
[paths]
overlay = ["pyproject.toml"]
mirror = ["pyproject.toml"]
generated = []
""".lstrip(),
    )
    with pytest.raises(CfgError, match="Invalid feature manifest content"):
        load_owner_manifest_index(cfg_root)


def test_payload_directories_define_files_but_not_generated_targets(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    # Repo-specific owners are implicit from inventory.
    _write(
        cfg_root / "repos" / "me" / "proj" / "cfg.toml",
        """
id = "me/proj"
features = []
""".lstrip(),
    )

    # Overlay bytes exist -> should infer `paths.overlay` includes ".cursor"
    _write(
        cfg_root / "repos" / "me" / "proj" / "overlay" / ".cursor" / "rules" / "x.mdc",
        "hello\n",
    )

    # Render bytes exist (template inputs) -> MUST NOT infer `paths.generated`.
    _write(
        cfg_root / "features" / "repo" / "a" / "render" / "fragments" / "fragment-a.txt",
        "a\n",
    )

    idx = load_owner_manifest_index(cfg_root)
    assert idx["repo/me/proj"].generated == ()
    files = owner_overlay_files(cfg_root=cfg_root, owner_id="repo/me/proj")
    assert [item.rel.as_posix() for item in files] == [".cursor/rules/x.mdc"]
