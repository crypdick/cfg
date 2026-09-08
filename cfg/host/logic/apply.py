from __future__ import annotations

from cfg.core.system_checks import ensure_gnu_stat_for_pyinfra
from cfg.host.cli_common import builtin_workflow_path, host_ctx, require_registered_host
from cfg.host.runner import run_pyinfra


def apply(
    *, host: str | None, dry_run: bool, yes: bool = False, quiet: bool = False, force: bool = False
) -> list[str]:
    """Business logic for `cfg host apply` (returns lines to print)."""
    # Pre-flight check: ensure GNU stat is configured for pyinfra
    # Print these immediately before any pyinfra output
    stat_messages = ensure_gnu_stat_for_pyinfra()
    for msg in stat_messages:
        print(  # noqa: T201 -- must flush before pyinfra subprocess writes to stdout
            msg,
            flush=True,
        )  # allow: print-statements

    ctx, host = host_ctx(host)
    require_registered_host(ctx, host)

    deploy = builtin_workflow_path("apply_home")
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
    return ["home applied."]
