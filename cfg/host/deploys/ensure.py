"""
Shared helpers for host deploys (pyinfra).

This module provides apt-specific helpers (like ensure_apt_repo) and re-exports
cross-platform helpers from cfg.host.deploys.pkg for convenience.
"""

from __future__ import annotations

import hashlib
import re
import shlex
from io import StringIO

from pyinfra.context import host
from pyinfra.facts.files import File, Sha256File
from pyinfra.operations import files, server

from cfg.core.errors import CfgError

# Re-export cross-platform helpers
from cfg.host.deploys.pkg import (
    is_linux,
)


def _source_path(filename: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", filename):
        raise CfgError(f"Invalid APT source filename: {filename!r}")
    return f"/etc/apt/sources.list.d/{filename}.list"


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

    Uses signed-by to scope trust to this repository instead of global apt-key trust.

    Args:
        key_url: URL of the ASCII-armored GPG key
        key_name: filename stem for the keyring (e.g. "hashicorp" -> /etc/apt/keyrings/hashicorp.gpg)
        repo_src: apt source line without options (e.g. "deb https://example.com/deb stable main")
        repo_filename: name for /etc/apt/sources.list.d/<filename>.list
        repo_options: extra apt source options (e.g. "arch=amd64"), merged with signed-by
    """
    source_path = _source_path(repo_filename)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", key_name):
        raise CfgError(f"Invalid APT key name: {key_name!r}")
    parts = repo_src.split(None, 1)
    if len(parts) != 2 or parts[0] not in {"deb", "deb-src"}:
        raise CfgError("APT source must start with deb or deb-src and contain a location")
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
                f"(wget -qO - {shlex.quote(key_url)} || curl -sSLf {shlex.quote(key_url)}) | gpg --dearmor -o {keyring_path}",
                f"chmod 644 {keyring_path}",
            ],
            _sudo=True,
        )

    # Build the options block: always include signed-by, optionally merge extras
    options = f"signed-by={keyring_path}"
    if repo_options:
        options = f"{repo_options} {options}"

    # Insert [options] after "deb" or "deb-src"
    signed_src = f"{parts[0]} [{options}] {parts[1]}"

    # Write the exact file content rather than appending (apt.repo only appends,
    # leaving stale entries behind when the source line changes).
    files.put(
        name=f"Add {key_name} APT repository",
        src=StringIO(f"{signed_src}\n"),
        dest=source_path,
        mode="0644",
        _sudo=True,
    )


def remove_apt_repo(*, repo_filename: str, expected_content: str) -> None:
    """Retire one explicitly named source only while its contents match the declaration.

    NOTE: docs/pyinfra-idioms.md, Source preparation documents this contract.
    Call from the owner's prepare.py before packages refresh their metadata.
    Network reachability and keyring paths are never ownership evidence.
    """
    path = _source_path(repo_filename)
    if not expected_content.strip():
        raise CfgError("Expected APT source content must be non-empty")
    if not is_linux():
        return
    info = host.get_fact(File, path=path)
    if info is None:
        return
    digest = host.get_fact(Sha256File, path=path)
    if info is False or digest != hashlib.sha256(expected_content.encode("utf-8")).hexdigest():
        raise CfgError(f"Refusing to remove modified APT source: {path}")
    files.file(name=f"Remove retired APT source: {repo_filename}", path=path, present=False, _sudo=True)
