"""
Host deploys: apply feature-contributed home files.

Behavior:
- For `@local`, create symlinks into this cfg repo (edit-in-place workflow).
- For non-local targets, upload files into the host home directory (`files.put`).

Safety:
- By default, we never overwrite existing non-link files when running in symlink mode
  (conflicts fail loudly).
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
from pyinfra.operations import files

from cfg.core.errors import CfgError
from cfg.core.ids import parse_host_name
from cfg.deploys.host_data import CFG_HOST_NAME, cfg_root_from_host_data, owner_ids_from_host_data
from cfg.host.deploys.ensure import reconcile_stale_apt_repos
from cfg.host.deploys.feature_deploys import deploy_features
from cfg.host.managed_home import HomePlan, managed_home_roots, resolve_host_home_plan
from cfg.owners.fs import OwnerFile


def _cleanup_stale_managed_symlinks(*, home: str, plan: HomePlan, roots: list[Path]) -> None:
    """
    Remove symlinks under $HOME that point into cfg-managed roots but are absent from the plan.
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
    - broken symlink "directories" may exist at paths such as ~/.config/git.
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

    owner_ids = owner_ids_from_host_data()

    home = host.get_fact(Home)
    if not home:
        raise CfgError("Cannot determine home directory for host.")

    # Host identity for host-specific managed home files.
    host_name_raw = str(host.data.get(CFG_HOST_NAME) or "").strip()
    if not host_name_raw:
        raise CfgError("Missing host identity (host.data._cfg_host_name).")
    try:
        host_name = parse_host_name(host_name_raw)
    except ValueError as e:
        raise CfgError(f"Invalid host identity: {e}") from e

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

    # Reconcile stale third-party apt repos before any feature deploy performs an apt
    # operation (a stale repo file breaks apt-get update system-wide; see
    # reconcile_stale_apt_repos docstring).
    reconcile_stale_apt_repos()

    # Run feature-specific deploys after home files are in place.
    deploy_features()
