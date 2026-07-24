from __future__ import annotations

from typing import TYPE_CHECKING

from cfg.core.inventory import load_inventory
from cfg.core.owners import resolve_host_owner_ids_for_host, resolve_repo_owner_ids

if TYPE_CHECKING:
    from pathlib import Path


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.lstrip(), encoding="utf-8")


def test_resolve_repo_owner_ids_is_repo_scoped(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    _write(
        cfg_root / "features" / "host" / "uv" / "feature.toml",
        """
        schema_version = 1
        requires = []
        conflicts = []
        generated = []
        """,
    )
    _write(
        cfg_root / "features" / "repo" / "python" / "feature.toml",
        """
        schema_version = 1
        requires = []
        conflicts = []
        generated = []
        """,
    )
    _write(
        cfg_root / "features" / "repo" / "uv" / "feature.toml",
        """
        schema_version = 1
        requires = ["python"]
        host_requires = ["uv"]
        conflicts = []
        generated = []
        """,
    )

    resolved = resolve_repo_owner_ids(cfg_root=cfg_root, enabled_repo_owner_ids=["repo/feature/uv"])
    assert resolved == ["repo/feature/python", "repo/feature/uv"]


def test_resolve_host_owner_ids_for_host_includes_repo_implied_host_deps(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    # Inventory: host has one attached repo whose owners include repo/feature/uv.
    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        """
        name = "h1"
        features = []
        [repos]
        "owner/repo" = "/tmp/repo"
        """,
    )
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
        id = "owner/repo"
        features = ["uv"]
        """,
    )
    # Feature manifests: repo/feature/uv requires host/feature/uv (cross-scope dependency).
    _write(
        cfg_root / "features" / "host" / "base" / "feature.toml",
        """
        schema_version = 1
        requires = []
        conflicts = []
        generated = []
        """,
    )
    _write(
        cfg_root / "features" / "host" / "uv" / "feature.toml",
        """
        schema_version = 1
        requires = []
        conflicts = []
        generated = []
        """,
    )
    _write(
        cfg_root / "features" / "repo" / "base" / "feature.toml",
        """
        schema_version = 1
        requires = []
        conflicts = []
        generated = []
        """,
    )
    _write(
        cfg_root / "features" / "repo" / "uv" / "feature.toml",
        """
        schema_version = 1
        requires = []
        host_requires = ["uv"]
        conflicts = []
        generated = []
        """,
    )

    inv = load_inventory(cfg_root)
    h1 = inv.hosts["h1"].settings

    resolved_host_owners = resolve_host_owner_ids_for_host(
        cfg_root=cfg_root, cfg_inventory=inv, host_settings=h1
    )
    assert resolved_host_owners == ["host/h1", "host/feature/base", "host/feature/uv"]
