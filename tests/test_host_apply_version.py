from __future__ import annotations

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


def publish(root: Path, raw_base: Path, version: str) -> None:
    manifest = root / "pyproject.toml"
    manifest.write_text(f'[project]\nname = "cfg"\nversion = "{version}"\n', encoding="utf-8")
    git(root, "add", "pyproject.toml")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", version)
    git(root, "push", "origin", "main")
    raw = raw_base / git(root, "rev-parse", "HEAD") / "pyproject.toml"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(manifest.read_bytes())


@pytest.fixture
def published_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    import cfg.host.apply_version as version_check

    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    publisher = tmp_path / "publisher"
    git(tmp_path, "clone", str(remote), str(publisher))
    git(publisher, "checkout", "-b", "main")
    raw_base = tmp_path / "raw"
    publish(publisher, raw_base, "0.2.2")
    monkeypatch.setattr(version_check, "_SOURCE_REPO", str(remote))
    monkeypatch.setattr(version_check, "_RAW_BASE", raw_base.as_uri())
    monkeypatch.setattr(version_check, "version", lambda _name: "0.2.2")
    return remote, publisher, raw_base


def test_apply_version_current_without_local_source(published_version: tuple[Path, Path, Path]) -> None:
    assert check_cfg_version() == "cfg version 0.2.2 is current"


def test_apply_version_reads_latest_commit_when_branch_url_is_stale(
    published_version: tuple[Path, Path, Path],
) -> None:
    _, publisher, raw_base = published_version
    stale = raw_base / "main" / "pyproject.toml"
    stale.parent.mkdir()
    stale.write_text('[project]\nversion = "0.2.2"\n', encoding="utf-8")
    publish(publisher, raw_base, "0.2.3")
    with pytest.raises(CfgError, match=r"0\.2\.3.*uv tool upgrade cfg"):
        check_cfg_version()


def test_apply_version_fails_when_remote_unavailable(
    published_version: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import cfg.host.apply_version as version_check

    monkeypatch.setattr(version_check, "_SOURCE_REPO", str(tmp_path / "missing.git"))
    with pytest.raises(CfgError, match="Cannot check latest cfg version"):
        check_cfg_version()
