"""System pre-flight checks for cfg operations.

pyinfra stat Issue
==================

Problem:
--------
pyinfra v3.6 has performance and correctness issues when /usr/bin/stat points to the
Rust-based uutils implementation. This occurs because pyinfra expects GNU stat's output format.

Symptoms:
- pyinfra operations run 2x slower (17s vs 8s for cfg host apply)
- pyinfra incorrectly detects hundreds of false changes in already-synced files
- Change detection fails, causing unnecessary re-application of files

Root Cause:
-----------
The coreutils-from-uutils package provides a Rust implementation with subtle output format
differences from GNU coreutils. pyinfra's internal operations rely on parsing GNU stat output.

Solution:
---------
This module automatically configures Debian's update-alternatives system to prefer GNU stat:

1. First-time setup: Installs both alternatives with GNU stat at priority 100 (higher)
2. Recovery: After package updates that revert to uutils, automatically switches back

Packages involved:
- gnu-coreutils: Provides /usr/bin/gnustat (works with pyinfra)
- coreutils-from-uutils: Provides /usr/lib/cargo/bin/coreutils/stat (causes issues)

Performance comparison:
- GNU stat: 8-10s, 0 false changes
- uutils stat: 17s, 268 false changes on identical runs

The coreutils-from-uutils package directly manages /usr/bin/stat and overwrites the
symlink during package updates, bypassing the alternatives system. This module detects
and recovers from such situations automatically.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from cfg.core.errors import CfgError


def _is_uutils_stat() -> bool:
    """Check if /usr/bin/stat is currently pointing to uutils implementation."""
    try:
        # Resolve the symlink to its actual target
        stat_path = Path("/usr/bin/stat").resolve()
        return "uutils" in str(stat_path) or "cargo" in str(stat_path)
    except (OSError, RuntimeError):
        return False


def _check_gnu_stat_available() -> bool:
    """Check if GNU stat is available at /usr/bin/gnustat."""
    return Path("/usr/bin/gnustat").exists()


def _check_update_alternatives_configured() -> bool:
    """Check if update-alternatives is configured for stat."""
    try:
        result = subprocess.run(
            ["update-alternatives", "--display", "stat"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    else:
        return result.returncode == 0


def ensure_gnu_stat_for_pyinfra() -> list[str]:
    """
    Ensure GNU stat is configured before running pyinfra.

    Automatically configures Debian's update-alternatives system to use GNU stat instead
    of uutils stat. This is necessary because pyinfra has performance and correctness
    issues with uutils stat (2x slower, false change detection).

    On first-time setup (update-alternatives never configured):
    - Installs both GNU stat and uutils stat as alternatives
    - Sets GNU stat as default with higher priority (100 vs 50)
    - Requires sudo (user will be prompted for password)

    On recovery (package updates reverted to uutils):
    - Simply switches back to GNU stat using existing alternatives config
    - Requires sudo (user will be prompted for password)

    Returns:
        List of user-facing messages about actions taken (printed immediately).

    Raises:
        CfgError: If GNU stat is not available or configuration fails.
    """
    messages: list[str] = []

    # If already using GNU stat, nothing to do
    if not _is_uutils_stat():
        return messages

    # Check if GNU stat is available
    if not _check_gnu_stat_available():
        raise CfgError(
            "uutils stat detected, but GNU stat not available.\n"
            "Install gnu-coreutils: sudo apt install gnu-coreutils"
        )

    # Check if update-alternatives is already configured
    if _check_update_alternatives_configured():
        # Alternatives is configured but pointing to wrong one, just switch it
        messages.append("Switching stat to GNU coreutils (package update reverted to uutils)...")
        try:
            subprocess.run(
                ["sudo", "update-alternatives", "--set", "stat", "/usr/bin/gnustat"],
                check=True,
                capture_output=True,
            )
            messages.append("✓ Switched to GNU stat")
        except subprocess.CalledProcessError as e:
            raise CfgError(
                f"Failed to switch to GNU stat: {e}\n"
                "Try manually: sudo update-alternatives --set stat /usr/bin/gnustat"
            ) from e
    else:
        # Need to set up alternatives from scratch (first-time setup)
        messages.append("Configuring stat command (first-time setup, requires sudo)...")

        try:
            # Remove existing symlink if it exists
            stat_path = Path("/usr/bin/stat")
            if stat_path.is_symlink() or stat_path.exists():
                subprocess.run(
                    ["sudo", "rm", str(stat_path)],
                    check=True,
                    capture_output=True,
                )

            # Install GNU stat alternative with priority 100
            subprocess.run(
                [
                    "sudo",
                    "update-alternatives",
                    "--install",
                    "/usr/bin/stat",
                    "stat",
                    "/usr/bin/gnustat",
                    "100",
                ],
                check=True,
                capture_output=True,
            )

            # Install uutils stat alternative with lower priority (if it exists)
            if Path("/usr/lib/cargo/bin/coreutils/stat").exists():
                subprocess.run(
                    [
                        "sudo",
                        "update-alternatives",
                        "--install",
                        "/usr/bin/stat",
                        "stat",
                        "/usr/lib/cargo/bin/coreutils/stat",
                        "50",
                    ],
                    check=False,
                    capture_output=True,
                )

            # Force selection of GNU stat
            subprocess.run(
                ["sudo", "update-alternatives", "--set", "stat", "/usr/bin/gnustat"],
                check=True,
                capture_output=True,
            )

            messages.append("✓ Configured stat to use GNU coreutils")
        except subprocess.CalledProcessError as e:
            raise CfgError(
                f"Failed to configure GNU stat: {e}\nSee cfg/core/system_checks.py docstring for details."
            ) from e

    return messages
