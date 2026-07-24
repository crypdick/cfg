"""
Shared helpers for accessing cfg-specific keys from pyinfra's `host.data`.

Host deploys read the data written by the host runtime inventory.
"""

from __future__ import annotations

from pathlib import Path

from pyinfra.context import host

from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId, parse_owner_id

# Constants for host.data keys
CFG_ROOT = "_cfg_root"
CFG_HOST_NAME = "_cfg_host_name"
CFG_HOST_OWNER_IDS = "_cfg_host_owner_ids"


def require_host_data(key: str) -> object:
    """Retrieve a required key from pyinfra's host.data, raising CfgError if missing."""
    v = host.data.get(key)
    if v is None or v == "":
        raise CfgError(f"Missing host.data.{key} (cfg runtime inventory not provided?)")
    return v


def cfg_root_from_host_data() -> Path:
    """Return the cfg root from host.data, resolved to an absolute path."""
    return Path(str(require_host_data(CFG_ROOT))).resolve()


def owner_ids_from_host_data() -> list[OwnerId]:
    """Parse the runtime inventory's owner list once at the pyinfra boundary."""
    raw = require_host_data(CFG_HOST_OWNER_IDS)
    if not isinstance(raw, list):
        raise CfgError("host.data._cfg_host_owner_ids must be a list[str]")
    try:
        return [parse_owner_id(str(owner_id)) for owner_id in raw]
    except ValueError as e:
        raise CfgError(f"Invalid host owner id in runtime inventory: {e}") from e
