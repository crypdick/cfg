from __future__ import annotations

from typing import TYPE_CHECKING

from cfg.core.deploy_discovery import discover_feature_deploy

if TYPE_CHECKING:
    from pathlib import Path


def test_discover_feature_deploy_ignores_non_host_and_missing_features(tmp_path: Path) -> None:
    assert discover_feature_deploy(tmp_path, "repo/feature/python") is None
    assert discover_feature_deploy(tmp_path, "host/laptop") is None
    assert discover_feature_deploy(tmp_path, "host/feature/missing") is None


def test_discover_feature_deploy_loads_main(tmp_path: Path) -> None:
    feature_dir = tmp_path / "features" / "host" / "example"
    feature_dir.mkdir(parents=True)
    (feature_dir / "feature.toml").write_text("schema_version = 1\n")
    (feature_dir / "deploy.py").write_text("def main():\n    return 'deployed'\n")

    deploy = discover_feature_deploy(tmp_path, "host/feature/example")

    assert deploy is not None
    assert deploy() == "deployed"


def test_discover_feature_deploy_requires_main(tmp_path: Path) -> None:
    feature_dir = tmp_path / "features" / "host" / "example"
    feature_dir.mkdir(parents=True)
    (feature_dir / "feature.toml").write_text("schema_version = 1\n")
    (feature_dir / "deploy.py").write_text("VALUE = 1\n")

    assert discover_feature_deploy(tmp_path, "host/feature/example") is None
