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

    Uses signed-by to scope trust to this repository instead of global apt-key trust.

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


def reconcile_stale_apt_repos() -> None:
    """
    Remove cfg-managed APT source files whose repo is no longer reachable (no-op on non-apt systems).

    Third-party repos added via `ensure_apt_repo` (NodeSource, HashiCorp, GitHub CLI,
    ProtonVPN, ...) can rot when upstream moves a dist path or codename (e.g. NodeSource
    dropping the `node_lts.x` alias). Once a stale file lands in
    `/etc/apt/sources.list.d/`, `apt-get update` fails system-wide until it's removed --
    blocking *every* subsequent apt operation, including ones unrelated to the broken repo,
    and even after the owning feature's `deploy.py` has been fixed to write correct
    contents (that fix can't take effect until an apt operation reaches it, which never
    happens if an earlier, unrelated apt operation dies first).

    Call this once, first thing, before any feature deploy performs an apt operation.
    Only touches files matching our own `signed-by=/etc/apt/keyrings/...` convention (i.e.
    files this module wrote), never hand-maintained or vendor-installed apt sources.
    """
    if not is_linux():
        return

    script = """
for f in /etc/apt/sources.list.d/*.list; do
    [ -f "$f" ] || continue
    grep -q "signed-by=/etc/apt/keyrings/" "$f" || continue
    rest="$(grep -m1 "^deb " "$f" | sed -E "s/^deb +\\[[^]]*\\] +//")"
    url="$(echo "$rest" | awk '{print $1}')"
    dist="$(echo "$rest" | awk '{print $2}')"
    [ -n "$url" ] && [ -n "$dist" ] || continue
    if ! (wget -q --spider "$url/dists/$dist/Release" 2>/dev/null \\
            || curl -fsSL -o /dev/null "$url/dists/$dist/Release" 2>/dev/null); then
        echo "Removing unreachable apt repo: $f ($url/dists/$dist/Release)" >&2
        rm -f "$f"
    fi
done
""".strip()

    server.shell(
        name="Remove unreachable cfg-managed APT repo files",
        commands=[script],
        _sudo=True,
    )
