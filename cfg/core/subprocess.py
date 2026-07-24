from __future__ import annotations

import subprocess
from pathlib import Path

from cfg.core.errors import CfgError


def run_cmd(
    argv: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    strip: bool = True,
) -> str:
    """
    Run a command and return stdout (stripped).
    Raises CfgError on failure when check=True.
    """
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as e:
        raise CfgError(f"Failed to run command: {' '.join(argv)} ({e})") from e

    if check and proc.returncode != 0:
        stderr = proc.stderr.strip()
        raise CfgError(f"Command failed ({proc.returncode}): {' '.join(argv)}\n{stderr}")

    return proc.stdout.strip() if strip else proc.stdout
