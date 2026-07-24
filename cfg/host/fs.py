"""
Host-specific (non-feature) filesystem layout helpers.

Host inventory entries (TOML) live under:
  hosts/<host>/cfg.toml

Host-specific payload (managed home files) lives under:
  hosts/<host>/overlay/<path-inside-home>
"""

from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.fs import iter_files
from cfg.core.ids import HostName, parse_host_name
from cfg.owners.fs import OwnerFile

HOST_HOME_PROVIDER = "@host"


def safe_host_slug(raw: str) -> HostName:
    """
    Validate a host name for use as a filesystem path segment.
    (Conservative: must be a single segment, no '..', non-empty.)
    """
    try:
        return parse_host_name(raw)
    except ValueError as e:
        raise CfgError(str(e)) from e


def host_home_root(cfg_root: Path, host: str) -> Path:
    return cfg_root / "hosts" / safe_host_slug(host) / "overlay"


def host_specific_home_files(cfg_root: Path, host: str) -> list[OwnerFile]:
    """
    Return host-specific home files as OwnerFiles.

    The provider name is a reserved sentinel: "@host".
    """
    root = host_home_root(cfg_root, host)
    out: list[OwnerFile] = []
    for src in iter_files(root):
        rel = src.relative_to(root)
        out.append(OwnerFile(owner=HOST_HOME_PROVIDER, src=src, rel=rel))
    return out
