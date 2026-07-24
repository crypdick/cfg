"""
Host deploys: apply feature-contributed home files.

Behavior:
- For `@local`, create symlinks into this cfg repo (edit-in-place workflow).
- For non-local targets, upload files into the host home directory (`files.put`).

Safety:
- By default, we never overwrite existing non-link files when running in symlink mode
  (mirrors legacy behavior: fail loudly on conflicts).
- Pass ``--force`` to ``cfg host apply`` to overwrite non-link files with symlinks
  (sets ``CFG_FORCE_LINKS=1`` in the pyinfra subprocess).
"""

from __future__ import annotations

import os
from pathlib import Path

from pyinfra.api.deploy import deploy
from pyinfra.context import host
from pyinfra.facts.files import Link
from pyinfra.facts.server import Home
from pyinfra.operations import files, server

from cfg.core.errors import CfgError
from cfg.deploys.host_data import CFG_HOST_NAME, CFG_HOST_OWNER_IDS, cfg_root_from_host_data
from cfg.host.deploys.feature_deploys import deploy_features
from cfg.host.deploys.pkg import pkg_update, pkg_upgrade
from cfg.host.managed_home import HomePlan, managed_home_roots, resolve_host_home_plan
from cfg.owners.fs import OwnerFile


def _cleanup_stale_managed_symlinks(*, home: str, plan: HomePlan, roots: list[Path]) -> None:
    """
    Remove symlinks under $HOME that point into cfg-managed roots but are no longer desired.
    """
    for rel in sorted(plan.all_known_rels):
        if rel in plan.desired:
            continue
        dest = f"{home}/{rel.as_posix()}"
        info = host.get_fact(Link, path=dest)
        if not info:
            continue
        link_target = str(info.get("link_target") or "")
        if not any(link_target.startswith(str(r)) for r in roots):
            continue
        files.link(
            name=f"Remove stale managed symlink: ~/{rel.as_posix()}",
            path=dest,
            present=False,
        )


def _ensure_parent_dirs_for_desired(*, home: str, desired: dict[Path, OwnerFile]) -> None:
    """
    Ensure parent directories exist for desired paths.

    Notes:
    - pyinfra's link op doesn't always create intermediate dirs reliably under local exec.
    - old cfg setups may leave broken symlink "directories" behind (eg ~/.config/git).
    """
    parent_dirs: set[Path] = set()
    for rel in desired:
        parent = rel.parent
        if str(parent) and parent != Path():
            parent_dirs.add(parent)

    for parent in sorted(parent_dirs, key=lambda p: p.as_posix()):
        parent_dest = f"{home}/{parent.as_posix()}"
        info = host.get_fact(Link, path=parent_dest)
        if info:
            # If a directory path is actually a symlink, and it's broken, remove it so we can create a real dir.
            link_target = str(info.get("link_target") or "")
            if link_target and not Path(link_target).exists():
                files.link(
                    name=f"Remove broken symlink directory: ~/{parent.as_posix()}",
                    path=parent_dest,
                    present=False,
                )

        files.directory(
            name=f"Ensure directory exists: ~/{parent.as_posix()}",
            path=parent_dest,
            present=True,
        )


def _apply_symlinks(*, home: str, desired: dict[Path, OwnerFile]) -> None:
    force = os.environ.get("CFG_FORCE_LINKS") == "1"
    for rel, tf in sorted(desired.items(), key=lambda kv: kv[0].as_posix()):
        dest = f"{home}/{rel.as_posix()}"
        files.link(
            name=f"Link ~/{rel.as_posix()} -> cfg inventory owner payload",
            path=dest,
            target=str(tf.src),
            symbolic=True,
            create_remote_dir=True,
            force=force,
        )


@deploy("host: apply home files from features")
def deploy_apply_home() -> None:
    cfg_root = cfg_root_from_host_data()

    # Install cfg tool from the local repo (editable) on local targets.
    if host.name == "@local":
        server.shell(
            name="Install cfg tool (editable)",
            commands=["uv tool install --force -e ."],
            _chdir=str(cfg_root),
        )

    owner_ids_raw = host.data.get(CFG_HOST_OWNER_IDS) or []
    if not isinstance(owner_ids_raw, list):
        raise CfgError("host.data._cfg_host_owner_ids must be a list[str]")
    owner_ids = [str(o).strip() for o in owner_ids_raw if str(o).strip()]

    home = host.get_fact(Home)
    if not home:
        raise CfgError("Cannot determine home directory for host.")

    # Host identity for host-specific managed home files.
    host_name = str(host.data.get(CFG_HOST_NAME) or "").strip()
    if not host_name:
        raise CfgError("Missing host identity (host.data._cfg_host_name).")

    plan: HomePlan = resolve_host_home_plan(cfg_root=cfg_root, host=host_name, enabled_owner_ids=owner_ids)
    roots = managed_home_roots(cfg_root)

    # Apply home files BEFORE running feature deploys.
    #
    # Why first: some feature deploys invoke binaries that auto-create config
    # files at overlay paths on first run (e.g. `claude plugin install` in the
    # obsidian feature triggers `claude` to write ~/.claude/settings.json). If
    # symlinks aren't already in place, those auto-creates land as real files
    # at overlay paths, and the later symlink phase refuses to clobber them
    # (collision -> apply fails, recreate-loop on every retry).
    # With symlinks first, the path resolves to the cfg-managed file before
    # any deploy touches it.
    if host.name == "@local":
        _cleanup_stale_managed_symlinks(home=home, plan=plan, roots=roots)
        _ensure_parent_dirs_for_desired(home=home, desired=plan.desired)
        _apply_symlinks(home=home, desired=plan.desired)
    else:
        # Non-local targets: upload files into the home directory.
        # Note: we intentionally do not attempt to "cleanup stale" here (no
        # persisted ownership model yet).
        for rel, tf in sorted(plan.desired.items(), key=lambda kv: kv[0].as_posix()):
            dest = f"{home}/{rel.as_posix()}"
            files.put(
                name=f"Upload ~/{rel.as_posix()}",
                src=str(tf.src),
                dest=dest,
                mode=True,
            )

    # Run feature-specific deploys after home files are in place.
    # These configure third-party APT repos (keyrings + sources.list.d) and
    # install feature-specific packages. Must run before the global apt
    # update/upgrade so stale repo entries are replaced before apt tries to
    # fetch from them.
    deploy_features()

    # Update package cache and upgrade installed packages (apt or brew).
    pkg_update()
    pkg_upgrade()
