"""
Cross-platform package management helpers for pyinfra deploys.

Provides a unified interface for package operations that works with both
apt (Debian/Ubuntu) and Homebrew (macOS).

Usage:
    from cfg.host.deploys.pkg import ensure_command, pkg_update, pkg_upgrade, pkg_install

    # Install a command, auto-detecting the package manager
    ensure_command(command="jq")

    # With explicit package names per platform
    ensure_command(
        command="rg",
        apt_packages=["ripgrep"],
        brew_packages=["ripgrep"],
    )

    # Refresh package metadata and install available package versions
    pkg_update()
    pkg_upgrade()

    # Install specific packages
    pkg_install(packages=["git", "curl"])
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from pyinfra.context import host
from pyinfra.facts.brew import BrewCasks
from pyinfra.facts.server import Kernel, Which
from pyinfra.operations import apt, brew, snap

from cfg.core.errors import CfgError


class HostOS(Enum):
    """Detected operating system."""

    LINUX = "Linux"
    MACOS = "Darwin"
    UNKNOWN = "unknown"


def detect_os() -> HostOS:
    """
    Detect the host operating system using the kernel name.

    Returns LINUX for Linux systems, MACOS for macOS/Darwin, or UNKNOWN.
    """
    kernel = host.get_fact(Kernel)
    if kernel == "Linux":
        return HostOS.LINUX
    if kernel == "Darwin":
        return HostOS.MACOS
    return HostOS.UNKNOWN


def is_linux() -> bool:
    """Return True if running on Linux."""
    return detect_os() == HostOS.LINUX


def is_macos() -> bool:
    """Return True if running on macOS."""
    return detect_os() == HostOS.MACOS


def _has_apt() -> bool:
    """Return True if apt-get is available (Linux package manager check)."""
    return bool(host.get_fact(Which, "apt-get"))


def _has_brew() -> bool:
    """Return True if Homebrew is available."""
    return bool(host.get_fact(Which, "brew"))


def pkg_update(*, name: str | None = None) -> None:
    """
    Update the package manager cache.

    On Linux (apt): runs `apt-get update`
    On macOS (brew): runs `brew update`
    """
    os = detect_os()
    if os == HostOS.LINUX and _has_apt():
        apt.update(name=name or "Update apt package cache", _sudo=True)
    elif os == HostOS.MACOS and _has_brew():
        brew.update(name=name or "Update Homebrew")


def pkg_upgrade(*, name: str | None = None) -> None:
    """
    Bring installed packages to the versions available from configured repositories.
    """
    os = detect_os()
    if os == HostOS.LINUX and _has_apt():
        apt.upgrade(name=name or "Upgrade installed packages", _sudo=True)
    elif os == HostOS.MACOS and _has_brew():
        brew.upgrade(name=name or "Upgrade Homebrew packages")


def pkg_install(
    *,
    packages: Sequence[str],
    apt_packages: Sequence[str] | None = None,
    brew_packages: Sequence[str] | None = None,
    name: str | None = None,
    update: bool = False,
    cache_time: int = 60 * 60 * 24,
) -> None:
    """
    Install packages using the appropriate package manager for the OS.

    Args:
        packages: Default package names (used if platform-specific list not provided)
        apt_packages: Override package names for apt (Linux)
        brew_packages: Override package names for Homebrew (macOS)
        name: Custom operation name
        update: Whether to update package cache before installing
        cache_time: For apt, cache validity in seconds (default 24h)
    """
    os = detect_os()

    if os == HostOS.LINUX:
        if not _has_apt():
            raise CfgError(
                f"Linux detected but apt-get not found. Cannot install: {', '.join(packages)}\n"
                "Fix: this system may need a different package manager (not yet supported)."
            )
        pkgs = list(apt_packages) if apt_packages is not None else list(packages)
        apt.packages(
            name=name or f"Install {', '.join(pkgs)} (apt)",
            packages=pkgs,
            update=update,
            cache_time=cache_time,
            _sudo=True,
        )

    elif os == HostOS.MACOS:
        if not _has_brew():
            raise CfgError(
                f"macOS detected but Homebrew not found. Cannot install: {', '.join(packages)}\n"
                "Fix: install Homebrew from https://brew.sh"
            )
        pkgs = list(brew_packages) if brew_packages is not None else list(packages)
        if not pkgs:
            return  # Nothing to install (e.g., command is built-in on macOS)
        brew.packages(
            name=name or f"Install {', '.join(pkgs)} (brew)",
            packages=pkgs,
            update=update,
        )

    else:
        raise CfgError(
            f"Unknown OS. Cannot install: {', '.join(packages)}\nFix: this platform is not yet supported."
        )


def ensure_command(
    *,
    command: str,
    apt_packages: Sequence[str] | None = None,
    brew_packages: Sequence[str] | None = None,
    install_name: str | None = None,
    required_message: str | None = None,
    builtin_on_macos: bool = False,
) -> None:
    """
    Ensure `command` exists on the target host.

    Cross-platform helper that supports both apt (Linux) and Homebrew (macOS):
    - If command exists: no-op
    - If missing on Linux: install via apt
    - If missing on macOS: install via brew
    - Otherwise: raise CfgError with guidance

    Args:
        command: The command to check for (e.g., "jq", "rg")
        apt_packages: Package names for apt (defaults to [command])
        brew_packages: Package names for brew (defaults to [command])
        install_name: Custom name for the install operation
        required_message: Custom error message if installation fails
        builtin_on_macos: If True, skip installation on macOS (command is built-in)
    """
    cmd = str(command).strip()
    if not cmd:
        raise CfgError("ensure_command: command must be non-empty")

    if host.get_fact(Which, command):
        return

    os = detect_os()

    if builtin_on_macos and os == HostOS.MACOS:
        return  # built-in; skip installation attempt

    if os == HostOS.LINUX:
        if not _has_apt():
            raise CfgError(
                required_message or f"{cmd} is required but apt-get not found on this Linux system."
            )
        pkgs = list(apt_packages) if apt_packages is not None else [cmd]
        apt.packages(
            name=install_name or f"Install {cmd} (apt)",
            packages=pkgs,
            update=True,
            cache_time=60 * 60 * 24,
            _sudo=True,
        )
        return

    if os == HostOS.MACOS:
        if not _has_brew():
            raise CfgError(
                required_message or f"{cmd} is required but Homebrew not found. Install from https://brew.sh"
            )
        pkgs = list(brew_packages) if brew_packages is not None else [cmd]
        if not pkgs:
            # No brew package needed (command should be built-in)
            return
        brew.packages(
            name=install_name or f"Install {cmd} (brew)",
            packages=pkgs,
            update=True,
        )
        return

    raise CfgError(
        required_message
        or (
            f"{cmd} is required but not installed, and this platform is not supported.\n\n"
            f"Fix: install {cmd} manually, then re-run.\n"
        )
    )


def brew_tap(*, tap: str, name: str | None = None) -> None:
    """
    Add a Homebrew tap (no-op on non-macOS systems).

    Args:
        tap: Name of the tap (e.g., "hashicorp/tap")
        name: Custom operation name
    """
    if not is_macos():
        return
    if not _has_brew():
        return
    brew.tap(
        name=name or f"Add Homebrew tap: {tap}",
        src=tap,
    )


def install_cask(
    *,
    cask: str,
    installed_name: str | None = None,
    tap: str | None = None,
    name: str | None = None,
) -> None:
    """
    Install a Homebrew cask idempotently (no-op on non-macOS systems).

    Args:
        cask: Cask spec passed to `brew install --cask`. May be tap-qualified
            (e.g. "nikitabobko/tap/aerospace").
        installed_name: Name as it appears in `brew list --cask`, used for the
            idempotency check. Defaults to the last path segment of `cask`.
        tap: Optional Homebrew tap to add before installing.
        name: Custom operation name.
    """
    if not is_macos():
        return

    check_name = installed_name or cask.rsplit("/", 1)[-1]
    installed_casks = host.get_fact(BrewCasks) or []
    if check_name in installed_casks:
        return

    if tap:
        brew_tap(tap=tap)

    brew.casks(
        name=name or f"Install {check_name} via Homebrew cask",
        casks=[cask],
    )


def remove_snap_package(*, package: str, name: str | None = None) -> None:
    """
    Remove a snap package if installed (Linux only).

    Uses pyinfra's native snap.package operation.

    Useful for packages where the snap version has issues (e.g., VPN clients
    may have connectivity detection problems due to snap confinement).

    Args:
        package: Name of the snap package to remove
        name: Custom operation name
    """
    if not is_linux():
        return

    # Check if snap is available on this system
    if not host.get_fact(Which, "snap"):
        return

    snap.package(
        name=name or f"Remove {package} snap if present",
        packages=[package],
        present=False,
        _sudo=True,
    )
