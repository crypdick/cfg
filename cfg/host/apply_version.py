"""Check the installed cfg version against its source repository."""

from __future__ import annotations

import json
import sysconfig
import tomllib
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from cfg.core.errors import CfgError
from cfg.core.subprocess import run_cmd


def _source_checkout(installed: str) -> Path:
    metadata = Path(sysconfig.get_path("purelib")) / f"cfg-{installed}.dist-info" / "direct_url.json"
    try:
        source = json.loads(metadata.read_text(encoding="utf-8"))
        url = urlparse(source["url"])
        if url.scheme != "file" or url.netloc not in ("", "localhost"):
            raise ValueError("installation source is not a local path")
        root = Path(url2pathname(url.path)).resolve()
        if not root.is_dir():
            raise ValueError(f"source checkout is missing: {root}")
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise CfgError(
            "Cannot identify cfg's source Git checkout. Install cfg from a local checkout "
            "with `uv tool install /path/to/cfg` before running `cfg host apply`."
        ) from error
    else:
        return root


def check_cfg_version(*, dry_run: bool) -> str:
    """Require installed version to match the version on the source remote's main branch."""
    installed = version("cfg")
    root = _source_checkout(installed)
    try:
        if not dry_run:
            run_cmd(["git", "fetch", "origin"], cwd=root)
        # NOTE: README "Use" documents origin/main as the cfg version source.
        raw = run_cmd(["git", "show", "refs/remotes/origin/main:pyproject.toml"], cwd=root)
        project = tomllib.loads(raw)["project"]
        latest = project["version"]
        if not isinstance(latest, str) or not latest:
            raise ValueError("missing project version")
    except (CfgError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        raise CfgError(f"Cannot check latest cfg version from origin/main: {error}") from error
    if installed != latest:
        raise CfgError(
            f"cfg {installed} differs from origin/main {latest}. Update the cfg source checkout, "
            "then run `uv tool upgrade cfg` before rerunning `cfg host apply`."
        )
    if dry_run:
        return f"cfg version {installed} matches local origin/main (not fetched)"
    return f"cfg version {installed} is current"
