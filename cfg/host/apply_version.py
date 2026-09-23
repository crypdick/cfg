"""Check the installed cfg version against the project repository."""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from urllib.request import urlopen

from cfg.core.errors import CfgError
from cfg.core.subprocess import run_cmd

# NOTE: README "Use" documents main's pyproject.toml as the cfg version source.
_SOURCE_REPO = "https://github.com/crypdick/cfg.git"
_RAW_BASE = "https://raw.githubusercontent.com/crypdick/cfg"


def check_cfg_version() -> str:
    """Require installed version to match the version published on main."""
    installed = version("cfg")
    try:
        remote_ref = run_cmd(["git", "ls-remote", _SOURCE_REPO, "refs/heads/main"]).split()
        if len(remote_ref) != 2 or remote_ref[1] != "refs/heads/main":
            raise ValueError("missing main branch")
        commit = remote_ref[0]
        if len(commit) not in (40, 64) or any(char not in "0123456789abcdef" for char in commit):
            raise ValueError("invalid main commit")
        # Commit URL avoids stale branch-name responses from the raw-file cache.
        with urlopen(f"{_RAW_BASE}/{commit}/pyproject.toml", timeout=10) as response:  # noqa: S310 -- fixed project URL
            project = tomllib.loads(response.read().decode("utf-8"))["project"]
        latest = project["version"]
        if not isinstance(latest, str) or not latest:
            raise ValueError("missing project version")
    except (CfgError, OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        raise CfgError(f"Cannot check latest cfg version: {error}") from error
    if installed != latest:
        raise CfgError(
            f"cfg {installed} differs from latest version {latest}. Run `uv tool upgrade cfg` "
            "before rerunning `cfg host apply`. If installed from a local checkout, update it first."
        )
    return f"cfg version {installed} is current"
