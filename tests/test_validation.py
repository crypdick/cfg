from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.validation import validate_configuration
from tests.test_repo_cli_more import _write, _write_feature_manifest

if TYPE_CHECKING:
    from pathlib import Path


def _valid_configuration(cfg_root: Path) -> None:
    _write(cfg_root / ".cfg-root", "")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/base")
    _write(
        cfg_root / "features" / "repo" / "base" / "feature.toml",
        'schema_version = 1\ngenerated = ["generated.txt"]\n',
    )
    _write(
        cfg_root / "features" / "repo" / "base" / "render" / "templates" / "generated.txt.j2",
        "generated for {{ _cfg.repo_id }}\n",
    )
    _write(
        cfg_root / "repos" / "owner" / "project" / "cfg.toml",
        'id = "owner/project"\nfeatures = []\n',
    )
    _write(
        cfg_root / "hosts" / "laptop" / "cfg.toml",
        'name = "laptop"\nfeatures = []\n[repos]\n"owner/project" = "/src/project"\n',
    )
    _write(
        cfg_root / "hosts" / "laptop" / "deploy.py",
        "def main():\n    return None\n",
    )


def test_validate_configuration_resolves_every_inventory_entry(tmp_path: Path) -> None:
    _valid_configuration(tmp_path)

    report = validate_configuration(tmp_path)

    assert report.hosts == 1
    assert report.repos == 1
    assert report.owners == 4


def test_validate_configuration_rejects_deploy_without_main(tmp_path: Path) -> None:
    _valid_configuration(tmp_path)
    _write(tmp_path / "hosts" / "laptop" / "deploy.py", "VALUE = 1\n")

    with pytest.raises(CfgError, match=r"deploy must define callable main\(\)"):
        validate_configuration(tmp_path)


def test_validate_configuration_checks_unused_generated_features(tmp_path: Path) -> None:
    _valid_configuration(tmp_path)
    _write(
        tmp_path / "features" / "repo" / "unused" / "feature.toml",
        'schema_version = 1\ngenerated = ["missing.txt"]\n',
    )

    with pytest.raises(CfgError, match="Missing generated template source"):
        validate_configuration(tmp_path)


def test_validate_configuration_checks_repo_host_requirements(tmp_path: Path) -> None:
    _valid_configuration(tmp_path)
    _write(
        tmp_path / "features" / "repo" / "tool" / "feature.toml",
        'schema_version = 1\nhost_requires = ["missing"]\n',
    )
    _write(
        tmp_path / "repos" / "owner" / "project" / "cfg.toml",
        'id = "owner/project"\nfeatures = ["tool"]\n',
    )

    with pytest.raises(CfgError, match="Feature not found: host/feature/missing"):
        validate_configuration(tmp_path)


def test_host_override_uses_canonical_owner_sequence(tmp_path: Path) -> None:
    _valid_configuration(tmp_path)
    _write(tmp_path / "features/host/base/overlay/x", "base")
    _write(tmp_path / "hosts/laptop/overlay/x", "host")
    assert validate_configuration(tmp_path).hosts == 1


def test_validate_rejects_invalid_preparation_entrypoint(tmp_path: Path) -> None:
    _valid_configuration(tmp_path)
    _write(tmp_path / "hosts/laptop/prepare.py", "VALUE = 1\n")
    with pytest.raises(CfgError, match=r"callable main\(\).*prepare.py"):
        validate_configuration(tmp_path)


def test_host_report_uses_same_overrides_as_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cfg.host.logic.managed import managed

    _valid_configuration(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(tmp_path))
    _write(tmp_path / "features/host/base/overlay/x", "base")
    _write(tmp_path / "hosts/laptop/overlay/x", "host")
    lines = managed(host="laptop")
    assert any("x" in line for line in lines)
    assert validate_configuration(tmp_path).hosts == 1
