"""Check the installed cfg version against the project repository."""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from urllib.request import urlopen

from cfg.core.errors import CfgError

# NOTE: README "Use" documents main's pyproject.toml as the cfg version source.
_VERSION_URL = "https://raw.githubusercontent.com/crypdick/cfg/main/pyproject.toml"


def check_cfg_version() -> str:
    """Require installed version to match the version published on main."""
    installed = version("cfg")
    try:
        with urlopen(_VERSION_URL, timeout=10) as response:
            project = tomllib.loads(response.read().decode("utf-8"))["project"]
        latest = project["version"]
        if not isinstance(latest, str) or not latest:
            raise ValueError("missing project version")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        raise CfgError(f"Cannot check latest cfg version: {error}") from error
    if installed != latest:
        raise CfgError(
            f"cfg {installed} differs from latest version {latest}. Run `uv tool upgrade cfg` "
            "before rerunning `cfg host apply`. If installed from a local checkout, update it first."
        )
    return f"cfg version {installed} is current"
