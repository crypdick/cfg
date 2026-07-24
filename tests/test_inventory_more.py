from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.inventory import load_inventory

if TYPE_CHECKING:
    from pathlib import Path


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_inventory_iter_skips_underscores_and_dot_dirs(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    # Should be ignored (underscore dir)
    _write(cfg_root / "hosts" / "_private" / "cfg.toml", 'name="_private"\n')
    # Should be ignored (dot dir)
    _write(cfg_root / "hosts" / ".hidden" / "cfg.toml", 'name=".hidden"\n')
    # Should be ignored (__pycache__)
    _write(
        cfg_root / "hosts" / "__pycache__" / "cfg.toml",
        'name="__pycache__"\n',
    )
    # Valid
    _write(cfg_root / "hosts" / "h4" / "cfg.toml", 'name="h4"\n')

    inv = load_inventory(cfg_root)
    assert set(inv.hosts.keys()) == {"h4"}


def test_inventory_invalid_toml_parse_error(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")
    _write(cfg_root / "hosts" / "h1" / "cfg.toml", "not = [toml\n")
    with pytest.raises(CfgError, match="Failed to parse TOML inventory file"):
        load_inventory(cfg_root)


def test_inventory_host_repos_and_vars_must_be_tables(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        """
name="h1"
repos = ["not-a-table"]
""".lstrip(),
    )
    with pytest.raises(CfgError, match="`repos` must be a table"):
        load_inventory(cfg_root)

    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        """
name="h1"
[repos]
"owner/repo"="/tmp/repo"
vars = ["not-a-table"]
""".lstrip(),
    )
    # Put `vars` at the top-level (after a table header it becomes part of that table).
    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        """
name="h1"
vars = ["not-a-table"]
[repos]
"owner/repo"="/tmp/repo"
""".lstrip(),
    )
    with pytest.raises(CfgError, match="`vars` must be a table"):
        load_inventory(cfg_root)


def test_inventory_repo_settings_table_rejected(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id="owner/repo"
[settings]
x=1
""".lstrip(),
    )
    with pytest.raises(CfgError, match=re.escape("settings") + ".*" + re.escape("no longer supported")):
        load_inventory(cfg_root)


def test_inventory_ignores_nested_repo_payload_named_cfg_toml(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")
    _write(cfg_root / "repos" / "owner" / "repo" / "extra" / "cfg.toml", "id='x/y'\n")
    assert load_inventory(cfg_root).repos == {}


def test_inventory_ignores_nested_host_payload_named_cfg_toml(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")
    _write(cfg_root / "hosts" / "h1" / "extra" / "cfg.toml", "name='h1'\n")
    assert load_inventory(cfg_root).hosts == {}


def test_inventory_ignores_cfg_toml_directories(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    # Directory named cfg.toml should be ignored by the inventory loader.
    d = cfg_root / "hosts" / "h1" / "cfg.toml"
    d.mkdir(parents=True, exist_ok=True)

    inv = load_inventory(cfg_root)
    assert inv.hosts == {}


def test_inventory_toml_read_error_is_user_friendly(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    p = cfg_root / "hosts" / "h1" / "cfg.toml"
    _write(p, 'name="h1"\n')
    os.chmod(p, 0)
    try:
        with pytest.raises(CfgError, match="Failed to read TOML inventory file"):
            load_inventory(cfg_root)
    finally:
        # Ensure cleanup so pytest can delete temp dirs.
        os.chmod(p, 0o644)


def test_inventory_wraps_host_and_repo_model_validation(tmp_path: Path) -> None:
    _write(
        tmp_path / "hosts" / "h1" / "cfg.toml",
        'name = "h1"\nfeatures = ["host/feature/desktop"]\n',
    )
    with pytest.raises(CfgError, match="Invalid host inventory TOML content"):
        load_inventory(tmp_path)

    (tmp_path / "hosts" / "h1" / "cfg.toml").unlink()
    _write(
        tmp_path / "repos" / "owner" / "repo" / "cfg.toml",
        'id = "owner/repo"\nfeatures = ["repo/feature/uv"]\n',
    )
    with pytest.raises(CfgError, match="Invalid repo inventory TOML content"):
        load_inventory(tmp_path)
