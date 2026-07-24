"""
pyinfra integration for host workflows.

`resolve_targets` maps the user-facing `--hosts` selector into pyinfra `--limit` tokens.
`run_pyinfra` shells out to pyinfra CLI while setting `CFG_ROOT` (falls back to a
generated temporary inventory if the static `inventory.py` is missing).
"""

from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.inventory import Inventory
from cfg.pyinfra.execute import run_pyinfra as _run_pyinfra
from cfg.pyinfra.runtime_inventory import cleanup_runtime_inventory, write_runtime_inventory


def resolve_targets(inv: Inventory, selector: str) -> list[str]:
    """
    Resolve a selector into pyinfra `--limit` tokens.

    Selector can be:
    - a host name (as defined in config)
    - a feature/group name (matches any host `features` entry)
    - a comma-separated list of either
    - special target: @local
    """
    selector = selector.strip()
    if not selector:
        raise CfgError("Missing --hosts selector")

    tokens = [t.strip() for t in selector.split(",") if t.strip()]
    hosts = [h.settings for h in inv.hosts.values()]

    by_name = {h.name: h for h in hosts}
    out: list[str] = []

    for tok in tokens:
        if tok == "@local":
            out.append("@local")
            continue

        if tok in by_name:
            out.append(tok)
            continue

        # treat as group
        group_targets = [str(h.name) for h in hosts if tok in (h.features or [])]
        if group_targets:
            out.extend(group_targets)
            continue

        raise CfgError(f"Unknown host/group selector: {tok}")

    # de-dup preserving order
    seen: set[str] = set()
    return [t for t in out if not (t in seen or seen.add(t))]


def _get_inventory_path(
    cfg_root: Path,
    cfg_inventory: Inventory,
    current_host_for_local: str | None,
    limit: list[str] | None,
) -> tuple[Path, Path | None]:
    """Get inventory path, creating temp file if needed. Returns (inv_path, tmpdir_to_cleanup)."""
    static_inventory = cfg_root / "inventory.py"
    if static_inventory.is_file():
        return static_inventory, None

    include_local = "@local" in (limit or [])
    inv_path, tmpdir = write_runtime_inventory(
        cfg_root=cfg_root,
        cfg_inventory=cfg_inventory,
        current_host_for_local=current_host_for_local,
        include_local=include_local,
    )
    return inv_path, tmpdir


def _run_with_inventory(
    *,
    cfg_root: Path,
    cfg_inventory: Inventory,
    limit: list[str] | None,
    operations: list[str],
    current_host_for_local: str | None,
    extra_env: dict[str, str] | None = None,
    dry_run: bool = False,
    quiet: bool = False,
) -> None:
    """Resolve the inventory, run pyinfra with `CFG_ROOT`/`CFG_HOST_FOR_LOCAL` set, and clean up."""
    inv_path, tmpdir = _get_inventory_path(cfg_root, cfg_inventory, current_host_for_local, limit)
    merged_env = {"CFG_ROOT": str(cfg_root), **dict(extra_env or {})}
    if current_host_for_local:
        merged_env["CFG_HOST_FOR_LOCAL"] = str(current_host_for_local)

    try:
        _run_pyinfra(
            cwd=cfg_root,
            inventory_path=inv_path,
            operations=operations,
            limit=limit,
            extra_env=merged_env,
            dry_run=dry_run,
            quiet=quiet,
        )
    finally:
        if tmpdir is not None:
            cleanup_runtime_inventory(tmpdir)


def run_pyinfra(
    *,
    cfg_root: Path,
    cfg_inventory: Inventory,
    limit: list[str],
    deploy_file: Path,
    current_host_for_local: str | None,
    extra_env: dict[str, str] | None = None,
    dry_run: bool = False,
    quiet: bool = False,
) -> None:
    _run_with_inventory(
        cfg_root=cfg_root,
        cfg_inventory=cfg_inventory,
        limit=limit,
        operations=[str(deploy_file)],
        current_host_for_local=current_host_for_local,
        extra_env=extra_env,
        dry_run=dry_run,
        quiet=quiet,
    )


def run_pyinfra_debug_inventory(
    *,
    cfg_root: Path,
    cfg_inventory: Inventory,
    limit: list[str] | None,
    current_host_for_local: str | None,
    extra_env: dict[str, str] | None = None,
) -> None:
    _run_with_inventory(
        cfg_root=cfg_root,
        cfg_inventory=cfg_inventory,
        limit=limit,
        operations=["debug-inventory"],
        current_host_for_local=current_host_for_local,
        extra_env=extra_env,
    )
