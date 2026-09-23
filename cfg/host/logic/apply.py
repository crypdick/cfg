from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.owners import resolve_host_owner_ids_for_host
from cfg.core.root import require_cfg_root
from cfg.core.state import read_host_state
from cfg.core.system_checks import ensure_gnu_stat_for_pyinfra
from cfg.host.apply_git_sync import sync_apply_root
from cfg.host.apply_version import check_cfg_version
from cfg.host.cli_common import builtin_workflow_path, host_ctx, require_registered_host
from cfg.host.managed_home import resolve_host_home_plan
from cfg.host.plan import (
    apply_host_cleanup,
    build_host_apply_plan,
    capture_host_state,
    format_host_cleanup,
)
from cfg.host.runner import run_pyinfra


def _refresh_interactive_sudo() -> None:
    """Prime native sudo timestamp so pyinfra does not reuse bad askpass data."""
    if not sys.stdin.isatty() or shutil.which("sudo") is None:
        return
    try:
        result = subprocess.run(["sudo", "-v"], check=False)
    except OSError as error:
        raise CfgError(f"Could not run sudo authentication preflight: {error}") from error
    if result.returncode != 0:
        raise CfgError("sudo authentication failed; host apply made no changes")


def apply(
    *, host: str | None, dry_run: bool, yes: bool = False, quiet: bool = False, force: bool = False
) -> list[str]:
    """Business logic for `cfg host apply` (returns lines to print)."""
    version_result = check_cfg_version()
    sync_result = sync_apply_root(require_cfg_root(), dry_run=dry_run)
    # Pre-flight check: ensure GNU stat is configured for pyinfra
    # Print these immediately before any pyinfra output
    stat_messages = ensure_gnu_stat_for_pyinfra()
    for msg in stat_messages:
        print(  # noqa: T201 -- must flush before pyinfra subprocess writes to stdout
            msg,
            flush=True,
        )  # allow: print-statements

    ctx, host = host_ctx(host)
    settings = require_registered_host(ctx, host)

    snapshot = ctx.snapshot
    owner_ids = resolve_host_owner_ids_for_host(
        cfg_root=ctx.root,
        cfg_inventory=snapshot.inventory,
        host_settings=settings,
        manifest_index=snapshot.manifest_index,
    )
    outputs = resolve_host_home_plan(
        cfg_root=ctx.root,
        host=settings.name,
        enabled_owner_ids=owner_ids,
        manifest_index=snapshot.manifest_index,
        host_vars=settings.vars,
    )
    plan = build_host_apply_plan(
        cfg_root=ctx.root,
        home=Path.home(),
        host=settings.name,
        outputs=outputs,
        previous_state=read_host_state(),
    )

    deploy = builtin_workflow_path("apply_home")
    if not dry_run:
        _refresh_interactive_sudo()
        apply_host_cleanup(plan)
    run_pyinfra(
        cfg_root=ctx.root,
        cfg_inventory=ctx.store.inventory,
        limit=["@local"],
        deploy_file=deploy,
        current_host_for_local=host,
        extra_env={"CFG_FORCE_LINKS": "1"} if force else None,
        dry_run=dry_run,
        auto_approve=yes,
        quiet=quiet,
    )
    if dry_run:
        return [
            version_result,
            f"personalization repo: {sync_result}",
            *format_host_cleanup(plan),
            "home apply planned.",
        ]
    state_path = capture_host_state(plan)
    return [
        version_result,
        f"personalization repo: {sync_result}",
        *format_host_cleanup(plan),
        f"state: {state_path}",
        "home applied.",
    ]
