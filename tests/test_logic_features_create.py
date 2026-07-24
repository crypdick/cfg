from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_feature_manifest(*, cfg_root: Path, owner_id: str) -> None:
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


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:owner/repo.git"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )


def _setup_cfg_root(tmp_path: Path, *, host_hint: str = "h1") -> Path:
    cfg_root = tmp_path / "cfg-root"
    _write(cfg_root / ".cfg-root", "")

    xdg = tmp_path / "xdg"
    _write(xdg / "cfg" / "root", str(cfg_root) + "\n")
    _write(xdg / "cfg" / "host", host_hint + "\n")

    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/desktop")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/uv")
    return cfg_root


def test_host_features_add_requires_host_registered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding a feature to an unregistered host should fail with helpful message."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from cfg.core.errors import CfgError
    from cfg.host.logic import features as host_features

    with pytest.raises(CfgError, match="Host not registered"):
        host_features.features_add(feature="desktop", host="unregistered-host", dry_run=False)


def test_repo_features_add_creates_repo_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    from cfg.repo.logic import features as repo_features

    out = repo_features.features_add(feature="uv", dry_run=False)
    assert out
    assert out[0].startswith("created:")

    inv = cfg_root / "repos" / "owner" / "repo" / "cfg.toml"
    data = tomllib.loads(inv.read_text(encoding="utf-8"))
    assert "uv" in (data.get("features") or [])


def test_host_features_create_basic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test creating a feature without dependencies."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from cfg.host.logic import features as host_features

    out = host_features.features_create(feature="my-feature", requires=[], dry_run=False)
    assert any("created:" in line for line in out)

    feature_toml = cfg_root / "features" / "host" / "my-feature" / "feature.toml"
    assert feature_toml.exists()

    data = tomllib.loads(feature_toml.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["requires"] == []


def test_host_features_create_with_base_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test creating a feature that requires base - this is valid for feature dependencies."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from cfg.host.logic import features as host_features

    # This should NOT raise - base is a valid dependency for features
    out = host_features.features_create(feature="my-feature", requires=["base"], dry_run=False)
    assert any("created:" in line for line in out)

    feature_toml = cfg_root / "features" / "host" / "my-feature" / "feature.toml"
    data = tomllib.loads(feature_toml.read_text(encoding="utf-8"))
    assert data["requires"] == ["base"]


def test_host_features_create_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test dry-run mode doesn't create files."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from cfg.host.logic import features as host_features

    out = host_features.features_create(feature="dry-feature", requires=["base"], dry_run=True)
    assert any("would create:" in line for line in out)

    feature_toml = cfg_root / "features" / "host" / "dry-feature" / "feature.toml"
    assert not feature_toml.exists()


def test_host_features_create_already_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error when feature already exists."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from cfg.core.errors import CfgError
    from cfg.host.logic import features as host_features

    # desktop feature already exists from _setup_cfg_root
    with pytest.raises(CfgError, match="already exists"):
        host_features.features_create(feature="desktop", requires=[], dry_run=False)


def test_host_features_add_requires_feature_in_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding a non-existent feature should fail with helpful message."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Create a host first
    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        'name = "h1"\nfeatures = []\n',
    )

    from cfg.core.errors import CfgError
    from cfg.host.logic import features as host_features

    with pytest.raises(CfgError, match="Feature not found"):
        host_features.features_add(feature="nonexistent", host="h1", dry_run=False)


def test_host_features_add_idempotent_already_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding a feature that's already enabled succeeds with 'ok' message."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Create a host with the feature already enabled
    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        'name = "h1"\nfeatures = ["desktop"]\n',
    )

    from cfg.host.logic import features as host_features

    out = host_features.features_add(feature="desktop", host="h1", dry_run=False)
    assert out
    assert "ok (already enabled)" in out[0]


def test_host_features_remove_idempotent_not_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing a feature that's not enabled succeeds with 'ok' message."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Create a host without the feature
    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        'name = "h1"\nfeatures = []\n',
    )

    from cfg.host.logic import features as host_features

    out = host_features.features_remove(feature="desktop", host="h1", dry_run=False)
    assert out
    assert "ok (not enabled)" in out[0]


def test_host_features_remove_requires_feature_in_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing a non-existent feature should fail (typo protection)."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Create a host
    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        'name = "h1"\nfeatures = []\n',
    )

    from cfg.core.errors import CfgError
    from cfg.host.logic import features as host_features

    with pytest.raises(CfgError, match="Feature not found"):
        host_features.features_remove(feature="typo-feature", host="h1", dry_run=False)


def test_host_features_delete_idempotent_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Deleting a feature that doesn't exist succeeds with 'ok' message."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from cfg.host.logic import features as host_features

    out = host_features.features_delete(feature="nonexistent", dry_run=False)
    assert out
    assert "ok (not found)" in out[0]


def test_repo_features_add_idempotent_already_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding a repo feature that's already enabled succeeds with 'ok' message."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    # Create repo inventory with feature already enabled
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        'id = "owner/repo"\norigin_url = "git@github.com:owner/repo.git"\nfeatures = ["uv"]\n',
    )

    from cfg.repo.logic import features as repo_features

    out = repo_features.features_add(feature="uv", dry_run=False)
    assert out
    assert "ok (already enabled)" in out[0]


def test_repo_features_remove_idempotent_not_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing a repo feature that's not enabled succeeds with 'ok' message."""
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    # Create repo inventory without the feature
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        'id = "owner/repo"\norigin_url = "git@github.com:owner/repo.git"\nfeatures = []\n',
    )

    from cfg.repo.logic import features as repo_features

    out = repo_features.features_remove(feature="uv", dry_run=False)
    assert out
    assert "ok (not enabled)" in out[0]
