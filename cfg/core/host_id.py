"""
Current-host identity for the *local machine*.

Many commands can take an explicit host argument (e.g. `cfg host apply my-laptop`),
but for convenience you can declare “this machine is host X” once.

Source of truth:
- `$XDG_CONFIG_HOME/cfg/host` (default: `~/.config/cfg/host`).
  This file is managed by `cfg` (usually via `cfg host init`); users should not need to edit it directly.
"""

from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.xdg import xdg_config_home


def cfg_host_hint_file() -> Path:
    return xdg_config_home() / "cfg" / "host"


def find_cfg_host() -> str | None:
    hint = cfg_host_hint_file()
    if hint.is_file():
        v = hint.read_text(encoding="utf-8").strip()
        return v or None

    return None


def require_cfg_host() -> str:
    host = find_cfg_host()
    if host:
        return host

    raise CfgError(
        "Could not determine current host.\n\n"
        "Fix one of:\n"
        "- register a host in inventory:\n"
        "  - `cfg host init <host>`\n"
        "- pass the host explicitly (e.g. `cfg host apply <host>`)\n"
    )


def set_cfg_host(host: str) -> Path:
    host = str(host).strip()
    if not host:
        raise CfgError("Host name must be non-empty")

    hint = cfg_host_hint_file()
    hint.parent.mkdir(parents=True, exist_ok=True)
    hint.write_text(host + "\n", encoding="utf-8")
    return hint
