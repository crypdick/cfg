from __future__ import annotations

import os
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.xdg import xdg_config_home


def _cfg_root_hint_file() -> Path:
    return xdg_config_home() / "cfg" / "root"


def _is_cfg_root(path: Path) -> bool:
    # Root marker file. Keeping this independent of inventory/config formats.
    return (path / ".cfg-root").is_file()


def _default_cfg_root() -> Path:
    return Path.home() / ".cfg"


def find_cfg_root(start: Path | None = None) -> Path | None:
    """
    Try to find the cfg personalization root.

    Resolution order:
    1) $CFG_ROOT env var
    2) ~/.config/cfg/root (or $XDG_CONFIG_HOME/cfg/root)
    3) walk upwards from `start` (defaults to CWD), looking for `.cfg-root`
    4) ~/.cfg
    """
    env_root = os.environ.get("CFG_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if _is_cfg_root(p):
            return p

    hint_file = _cfg_root_hint_file()
    if hint_file.is_file():
        raw = hint_file.read_text(encoding="utf-8").strip()
        if raw:
            p = Path(raw).expanduser().resolve()
            if _is_cfg_root(p):
                return p

    cur = (start or Path.cwd()).resolve()
    for parent in (cur, *cur.parents):
        if _is_cfg_root(parent):
            return parent

    default_root = _default_cfg_root().resolve()
    if _is_cfg_root(default_root):
        return default_root

    return None


def require_cfg_root(start: Path | None = None) -> Path:
    root = find_cfg_root(start=start)
    if root:
        return root

    hint_file = _cfg_root_hint_file()
    raise CfgError(
        "Could not locate cfg root.\n\n"
        "Fix one of:\n"
        f"- set CFG_ROOT=/path/to/cfg\n"
        f"- write the cfg root path to {hint_file}\n"
        "- create ~/.cfg as a personalization repository containing .cfg-root\n"
        "- run `cfg` from inside a personalization repository containing .cfg-root\n"
    )
