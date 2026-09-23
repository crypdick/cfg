from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.host.apply_version import check_cfg_version

if TYPE_CHECKING:
    from pathlib import Path


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def publish_version(root: Path, version: str) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "cfg"\nversion = "{version}"\n', encoding="utf-8"
    )
    git(root, "add", "pyproject.toml")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", version)
    git(root, "push", "origin", "main")


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    import cfg.host.apply_version as version_check

    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    checkout = tmp_path / "source"
    git(tmp_path, "clone", str(remote), str(checkout))
    git(checkout, "checkout", "-b", "main")
    publish_version(checkout, "0.2.1")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-b", "main", str(remote), str(other))

    site = tmp_path / "site"
    metadata = site / "cfg-0.2.1.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "direct_url.json").write_text(
        json.dumps({"url": checkout.as_uri(), "dir_info": {"editable": True}}), encoding="utf-8"
    )
    monkeypatch.setattr(version_check, "version", lambda _name: "0.2.1")
    monkeypatch.setattr(version_check.sysconfig, "get_path", lambda _name: str(site))
    return checkout, other


def test_apply_version_current(source: tuple[Path, Path]) -> None:
    assert check_cfg_version(dry_run=False) == "cfg version 0.2.1 is current"


def test_apply_version_rejects_newer_remote(source: tuple[Path, Path]) -> None:
    _, other = source
    publish_version(other, "0.2.2")
    with pytest.raises(CfgError, match=r"0\.2\.2.*uv tool upgrade cfg"):
        check_cfg_version(dry_run=False)


def test_apply_version_dry_run_uses_local_snapshot(source: tuple[Path, Path]) -> None:
    checkout, other = source
    publish_version(other, "0.2.2")
    assert check_cfg_version(dry_run=True) == "cfg version 0.2.1 matches local origin/main (not fetched)"
    assert git(checkout, "rev-parse", "origin/main") != git(other, "rev-parse", "HEAD")


@pytest.mark.usefixtures("source")
def test_apply_version_requires_local_source_checkout(tmp_path: Path) -> None:
    (tmp_path / "site/cfg-0.2.1.dist-info/direct_url.json").unlink()
    with pytest.raises(CfgError, match="Cannot identify cfg's source Git checkout"):
        check_cfg_version(dry_run=False)
