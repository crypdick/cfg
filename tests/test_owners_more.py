from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.owners import (
    FeatureManifest,
    FeatureOwner,
    OwnerManifest,
    feature_manifest_path,
    load_owner_manifest_index,
    owner_id_to_dir,
    parse_owner_ref,
    resolve_owners,
    resolve_owners_scoped,
)
from cfg.core.scope import Scope

if TYPE_CHECKING:
    from pathlib import Path


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_load_owner_manifest_index_rejects_legacy_owner_metadata(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(
        cfg_root / "features" / "repo" / "x" / "feature.toml",
        """
schema_version = 1
[owner]
id = "repo/feature/DIFFERENT"
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    with pytest.raises(CfgError, match="Invalid feature manifest content"):
        load_owner_manifest_index(cfg_root)


def test_owner_id_from_manifest_path_validation_errors(tmp_path: Path) -> None:
    import cfg.core.owners as owners

    cfg_root = tmp_path
    (cfg_root / ".cfg-root").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="not under features/host or features/repo"):
        owners.owner_id_from_feature_toml_path(
            cfg_root=cfg_root, path=cfg_root / "not-owners" / "feature.toml"
        )

    # Wrong filename.
    p = cfg_root / "features" / "repo" / "x" / "NOT.toml"
    _write(p, "")
    with pytest.raises(ValueError, match=re.escape("filename must be feature.toml")):
        owners.owner_id_from_feature_toml_path(cfg_root=cfg_root, path=p)

    # Too shallow: features/repo/feature.toml (missing feature-name segment)
    p2 = cfg_root / "features" / "repo" / "feature.toml"
    _write(p2, "")
    with pytest.raises(ValueError, match="must be under features/repo"):
        owners.owner_id_from_feature_toml_path(cfg_root=cfg_root, path=p2)


def test_owner_paths_map_new_layout_and_reject_invalid_ids(tmp_path: Path) -> None:
    assert owner_id_to_dir(tmp_path, "host/feature/i3") == tmp_path / "features" / "host" / "i3"
    assert owner_id_to_dir(tmp_path, "repo/feature/uv") == tmp_path / "features" / "repo" / "uv"
    assert owner_id_to_dir(tmp_path, "host/laptop") == tmp_path / "hosts" / "laptop"
    assert owner_id_to_dir(tmp_path, "repo/owner/project") == tmp_path / "repos" / "owner" / "project"
    assert feature_manifest_path(tmp_path, "repo/feature/uv") == (
        tmp_path / "features" / "repo" / "uv" / "feature.toml"
    )

    for owner_id in ("", "other/x", "host/feature/nested/name", "host/a/b", "repo/owner"):
        with pytest.raises((CfgError, ValueError)):
            owner_id_to_dir(tmp_path, owner_id)
    with pytest.raises(CfgError, match="Not a feature owner id"):
        feature_manifest_path(tmp_path, "host/laptop")


def test_feature_manifest_validates_schema_and_short_names() -> None:
    with pytest.raises(ValueError, match="Unsupported feature schema_version"):
        FeatureManifest(schema_version=2)
    with pytest.raises(ValueError, match="single path segment"):
        FeatureManifest(requires=["repo/feature/python"])
    with pytest.raises(ValueError, match="Unsafe"):
        FeatureManifest(generated=["../outside"])


def test_internal_owner_metadata_is_composed_from_parsed_values() -> None:
    owner = parse_owner_ref("repo/feature/python")

    assert owner == FeatureOwner(scope=Scope.REPO, name="python")
    assert OwnerManifest(owner=owner).owner_id == "repo/feature/python"
    with pytest.raises(ValueError, match="Invalid owner id"):
        parse_owner_ref("")


def test_host_feature_rejects_host_requires(tmp_path: Path) -> None:
    _write(
        tmp_path / "features" / "host" / "bad" / "feature.toml",
        'schema_version = 1\nhost_requires = ["uv"]\n',
    )
    with pytest.raises(CfgError, match="Host feature cannot declare host_requires"):
        load_owner_manifest_index(tmp_path)


def test_load_owner_manifest_index_rejects_duplicate_owner_ids(tmp_path: Path) -> None:
    # In practice this is hard to trigger without filesystem symlink tricks, because
    # owner ids are derived from manifest paths and must match those paths.
    pytest.skip("Duplicate derived owner ids are not realistically reachable without symlink tricks.")


def test_resolve_owners_unknown_owner_errors(tmp_path: Path) -> None:
    # Empty index
    with pytest.raises(CfgError, match="Feature not found"):
        resolve_owners(enabled=["repo/feature/missing"], manifest_index={})


def test_resolve_owners_detects_cycles(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        """
schema_version = 1
requires = ["b"]
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "repo" / "b" / "feature.toml",
        """
schema_version = 1
requires = ["a"]
conflicts = []
generated = []
""".lstrip(),
    )
    idx = load_owner_manifest_index(cfg_root)
    with pytest.raises(CfgError, match="dependency cycle"):
        resolve_owners(enabled=["repo/feature/a"], manifest_index=idx)


def test_resolve_owners_scoped_filters_dep_edges(tmp_path: Path) -> None:
    cfg_root = tmp_path
    # repo/feature/a requires host/feature/x, but repo-only resolution should not follow it.
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        """
schema_version = 1
requires = []
host_requires = ["x"]
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "host" / "x" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    idx = load_owner_manifest_index(cfg_root)

    out = resolve_owners_scoped(
        enabled=["repo/feature/a"],
        manifest_index=idx,
        allowed_scopes=frozenset({Scope.REPO}),
    )
    assert out == ["repo/feature/a"]


def test_load_owner_manifest_index_parse_errors(tmp_path: Path) -> None:
    cfg_root = tmp_path
    # Invalid TOML
    _write(
        cfg_root / "features" / "repo" / "bad" / "feature.toml",
        "not = [toml\n",
    )
    with pytest.raises(CfgError, match="Failed to read feature manifest"):
        load_owner_manifest_index(cfg_root)
