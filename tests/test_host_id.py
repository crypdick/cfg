from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.host_id import cfg_host_hint_file, find_cfg_host, require_cfg_host, set_cfg_host

if TYPE_CHECKING:
    from pathlib import Path


def test_host_hint_file_uses_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert cfg_host_hint_file() == tmp_path / "xdg" / "cfg" / "host"


def test_set_and_find_cfg_host_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    assert find_cfg_host() is None
    hint = set_cfg_host("my-host")
    assert hint.is_file()
    assert hint.read_text(encoding="utf-8") == "my-host\n"
    assert find_cfg_host() == "my-host"


def test_require_cfg_host_errors_without_instructing_hint_path_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    with pytest.raises(CfgError) as ei:
        require_cfg_host()

    msg = str(ei.value)
    assert "Could not determine current host" in msg
    assert "cfg host init" in msg


def test_set_cfg_host_rejects_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    with pytest.raises(CfgError, match="non-empty"):
        set_cfg_host("   ")
