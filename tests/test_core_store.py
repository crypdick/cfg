from __future__ import annotations

import tomllib
from pathlib import Path

from cfg.core.models import HostSettings, RepoSettings, SshSettings
from cfg.core.store import InventoryStore


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_feature_manifest(*, cfg_root: Path, owner_id: str) -> None:
    """Create a minimal feature owner manifest so owner resolution can succeed in tests."""
    parts = owner_id.split("/")
    assert len(parts) >= 3, owner_id
    assert parts[1] == "feature", owner_id
    scope = parts[0]
    rel = Path(*parts[2:])
    path = cfg_root / "features" / scope / rel / "feature.toml"
    _write(
        path,
        ("schema_version = 1\nrequires = []\nconflicts = []\ngenerated = []\n"),
    )


def test_store_save_repo_includes_optional_fields(tmp_path: Path) -> None:
    cfg_root = tmp_path
    (cfg_root / ".cfg-root").write_text("", encoding="utf-8")

    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/uv")

    store = InventoryStore(cfg_root)
    repo = RepoSettings(
        id="owner/repo",
        origin_url=" git@github.com:owner/repo.git ",
        alias="r",
        features=["uv"],
        path_provider_overrides={"a.txt": "repo/feature/base"},
    )
    path = store.save_repo(repo)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == "owner/repo"
    assert data["origin_url"] == "git@github.com:owner/repo.git"
    assert data["alias"] == "r"
    assert data["features"] == ["uv"]
    assert data["path_provider_overrides"] == {"a.txt": "repo/feature/base"}
    # Store writes repo settings under the canonical layout.
    assert path == cfg_root / "repos" / "owner" / "repo" / "cfg.toml"


def test_store_save_host_includes_optional_fields(tmp_path: Path) -> None:
    cfg_root = tmp_path
    (cfg_root / ".cfg-root").write_text("", encoding="utf-8")

    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/desktop")

    store = InventoryStore(cfg_root)
    host = HostSettings(
        name="h1",
        features=["desktop"],
        ssh=SshSettings(host="example.com", user="me", port=2222),
        repos={"owner/repo": Path("/tmp/repo")},
        vars={"x": 1},
    )
    path = store.save_host(host)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "h1"
    assert data["features"] == ["desktop"]
    assert data["ssh"] == {"host": "example.com", "user": "me", "port": 2222}
    assert data["repos"] == {"owner/repo": "/tmp/repo"}
    assert data["vars"] == {"x": 1}
    # Store writes host settings under the canonical layout.
    assert path == cfg_root / "hosts" / "h1" / "cfg.toml"
