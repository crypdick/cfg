from __future__ import annotations

from pathlib import Path

import pytest
import typer

from cfg.core.cli_helpers import resolve_relative_user_path
from cfg.core.errors import CfgError
from cfg.host.managed_home import resolve_host_home_plan


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_resolve_home_relpath_relative_is_relative_to_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    assert resolve_relative_user_path(base_dir=home, user_path=".config/foo") == Path(".config/foo")


def test_resolve_home_relpath_absolute_must_be_inside_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    inside = home / ".config" / "x"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text("x", encoding="utf-8")

    assert resolve_relative_user_path(base_dir=home, user_path=str(inside)) == Path(".config/x")

    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(typer.BadParameter, match="inside base directory"):
        resolve_relative_user_path(base_dir=home, user_path=str(outside))


def test_resolve_host_home_plan_detects_owner_conflicts(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / "features" / "host" / "a" / "overlay" / "x.txt", "a\n")
    _write(cfg_root / "features" / "host" / "b" / "overlay" / "x.txt", "b\n")
    _write(
        cfg_root / "features" / "host" / "a" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "host" / "b" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )

    with pytest.raises(CfgError, match="conflict"):
        resolve_host_home_plan(
            cfg_root=cfg_root, host="h1", enabled_owner_ids=["host/feature/a", "host/feature/b"]
        )


def test_resolve_host_home_plan_host_specific_overrides_tags(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / "features" / "host" / "a" / "overlay" / "x.txt", "a\n")
    _write(
        cfg_root / "features" / "host" / "a" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    _write(cfg_root / "hosts" / "h1" / "overlay" / "x.txt", "host\n")

    plan = resolve_host_home_plan(cfg_root=cfg_root, host="h1", enabled_owner_ids=["host/feature/a"])
    assert plan.desired[Path("x.txt")].owner == "@host"
    assert plan.desired[Path("x.txt")].src.read_text(encoding="utf-8") == "host\n"
