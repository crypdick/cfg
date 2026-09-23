from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.host.apply_version import check_cfg_version

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def published_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import cfg.host.apply_version as version_check

    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname = "cfg"\nversion = "0.2.1"\n', encoding="utf-8")
    monkeypatch.setattr(version_check, "_VERSION_URL", manifest.as_uri())
    monkeypatch.setattr(version_check, "version", lambda _name: "0.2.1")
    return manifest


@pytest.mark.usefixtures("published_version")
def test_apply_version_current_from_package_install() -> None:
    assert check_cfg_version() == "cfg version 0.2.1 is current"


def test_apply_version_rejects_newer_remote(published_version: Path) -> None:
    published_version.write_text('[project]\nname = "cfg"\nversion = "0.2.2"\n', encoding="utf-8")
    with pytest.raises(CfgError, match=r"0\.2\.2.*uv tool upgrade cfg"):
        check_cfg_version()


def test_apply_version_fails_when_remote_unavailable(published_version: Path) -> None:
    published_version.unlink()
    with pytest.raises(CfgError, match="Cannot check latest cfg version"):
        check_cfg_version()
