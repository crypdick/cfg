"""
Shared pyinfra execution helpers.

Provides a common interface for running pyinfra CLI from Python.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.pyinfra._vfork import VFORK_SOURCE_SNIPPET

# Disable the Python 3.13 vfork fast-path in the spawned interpreter, then run pyinfra.
PYINFRA_BOOTSTRAP = VFORK_SOURCE_SNIPPET + "\nfrom pyinfra_cli.main import main\nmain()"

# Default timeout for pyinfra CLI operations (seconds).
# Override with CFG_PYINFRA_TIMEOUT env var. Set to 0 to disable.
DEFAULT_PYINFRA_TIMEOUT = 300


def _get_timeout(env: dict[str, str] | None = None) -> int | None:
    """Get pyinfra timeout from env or use default. Returns None if disabled (0)."""
    env = env if env is not None else dict(os.environ)
    raw = (env.get("CFG_PYINFRA_TIMEOUT") or "").strip()
    if raw:
        try:
            val = int(raw)
        except ValueError:
            pass
        else:
            return val if val > 0 else None
    return DEFAULT_PYINFRA_TIMEOUT


def run_pyinfra_cli(
    *,
    cwd: Path,
    inventory_path: Path,
    operations: list[str],
    limit: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    dry_run: bool = False,
    quiet: bool = False,
) -> None:
    """
    Run pyinfra CLI with the given inventory and operations.

    Args:
        cwd: Working directory for the pyinfra process
        inventory_path: Path to inventory.py file
        operations: List of deploy files or commands (e.g. ["deploy.py"] or ["debug-inventory"])
        limit: Optional list of --limit targets
        extra_env: Optional extra environment variables
        quiet: If False (default), run pyinfra with verbose output (-v)
    """
    env = dict(os.environ)
    env.update(extra_env or {})

    cmd = [sys.executable, "-c", PYINFRA_BOOTSTRAP]
    if not sys.stdin.isatty():
        # Non-interactive (eg CI): don't prompt for confirmation.
        cmd.append("--yes")
    if dry_run:
        cmd.append("--dry")
    if not quiet:
        cmd.append("-v")
    for limiter in limit or []:
        cmd.extend(["--limit", limiter])
    cmd.append(str(inventory_path))
    cmd.extend(operations)

    timeout = _get_timeout(env)
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise CfgError(
            f"pyinfra timed out after {timeout}s. This often indicates a hanging command "
            f"(e.g., broken 'stat' binary). Set CFG_PYINFRA_TIMEOUT=0 to disable timeout, "
            f"or CFG_PYINFRA_TIMEOUT=N to increase it."
        ) from None
    if proc.returncode != 0:
        raise CfgError(f"pyinfra failed with exit code {proc.returncode}")


def run_pyinfra(
    *,
    cwd: Path,
    inventory_path: Path,
    operations: list[str],
    limit: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    dry_run: bool = False,
    quiet: bool = False,
) -> None:
    """Run pyinfra through the supported subprocess CLI path."""
    run_pyinfra_cli(
        cwd=cwd,
        inventory_path=inventory_path,
        operations=operations,
        limit=limit,
        extra_env=extra_env,
        dry_run=dry_run,
        quiet=quiet,
    )
