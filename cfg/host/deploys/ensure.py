"""
Shared helpers for host deploys (pyinfra).

This module provides apt-specific helpers (like ensure_apt_repo) and re-exports
cross-platform helpers from cfg.host.deploys.pkg for convenience.
"""

from __future__ import annotations

from io import StringIO

from pyinfra.context import host
from pyinfra.facts.files import File
from pyinfra.operations import files, server

# Re-export cross-platform helpers
from cfg.host.deploys.pkg import (
    is_linux,
)


def ensure_apt_repo(
    *,
    key_url: str,
    key_name: str,
    repo_src: str,
    repo_filename: str,
    repo_options: str = "",
) -> None:
    """
    Add a third-party APT repository with a signed GPG keyring (no-op on non-apt systems).

    Uses the modern signed-by approach (not the deprecated apt-key).

    Args:
        key_url: URL of the ASCII-armored GPG key
        key_name: filename stem for the keyring (e.g. "hashicorp" -> /etc/apt/keyrings/hashicorp.gpg)
        repo_src: apt source line without options (e.g. "deb https://example.com/deb stable main")
        repo_filename: name for /etc/apt/sources.list.d/<filename>.list
        repo_options: extra apt source options (e.g. "arch=amd64"), merged with signed-by
    """
    # No-op on non-Linux systems (allows unconditional calls in cross-platform code)
    if not is_linux():
        return

    files.directory(
        name="Ensure /etc/apt/keyrings directory exists",
        path="/etc/apt/keyrings",
        mode="0755",
        _sudo=True,
    )

    keyring_path = f"/etc/apt/keyrings/{key_name}.gpg"
    if not host.get_fact(File, keyring_path):
        server.shell(
            name=f"Download {key_name} GPG key",
            commands=[
                f"(wget -qO - {key_url} || curl -sSLf {key_url}) | gpg --dearmor -o {keyring_path}",
                f"chmod 644 {keyring_path}",
            ],
            _sudo=True,
        )

    # Build the options block: always include signed-by, optionally merge extras
    options = f"signed-by={keyring_path}"
    if repo_options:
        options = f"{repo_options} {options}"

    # Insert [options] after "deb" or "deb-src"
    parts = repo_src.split(None, 1)
    signed_src = f"{parts[0]} [{options}] {parts[1]}"

    # Write the exact file content rather than appending (apt.repo only appends,
    # leaving stale entries behind when the source line changes).
    files.put(
        name=f"Add {key_name} APT repository",
        src=StringIO(f"{signed_src}\n"),
        dest=f"/etc/apt/sources.list.d/{repo_filename}.list",
        mode="0644",
        _sudo=True,
    )
