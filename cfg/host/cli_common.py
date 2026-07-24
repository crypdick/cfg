from __future__ import annotations

from pathlib import Path

from cfg.core.context import CfgContext
from cfg.core.errors import CfgError
from cfg.core.models import HostSettings, safe_relpath
from cfg.core.protocols import HostCtxLike


def builtin_workflow_path(name: str) -> Path:
    """Return a workflow shipped with the installed cfg package."""
    return (Path(__file__).resolve().parent / "workflows" / f"{name}.py").resolve()


def host_ctx(host: str | None) -> tuple[CfgContext, str]:
    ctx = CfgContext.load()
    return ctx, (host or ctx.host_name)


def require_registered_host(
    ctx: HostCtxLike,
    host: str,
    *,
    include_hint: bool = False,
) -> HostSettings:
    settings = ctx.store.get_host(host)
    if settings:
        return settings
    msg = f"Host not registered: {host}"
    if include_hint:
        hint = ctx.store.get_host_path(host)
        msg += f"\nExpected: {hint}\nFix: cfg host init {host}"
    raise CfgError(msg)


def resolve_workflow_path(cfg_root: Path, workflow: str) -> Path:
    """
    Resolve a workflow argument into a deploy file path.

    - If `workflow` looks like a path, treat it as a path (relative to cfg root if not absolute).
    - Otherwise, treat it as a workflow name shipped with the installed cfg package.
    """
    w = str(workflow).strip()
    if not w:
        raise CfgError("Workflow name cannot be empty")

    # Path mode (explicit).
    if "/" in w or w.endswith(".py"):
        p = Path(w)
        if not p.is_absolute():
            p = cfg_root / safe_relpath(w)
        p = p.resolve()
        if not p.is_file():
            raise CfgError(f"Workflow file missing: {p}")
        return p

    # Name mode: built-in workflow from the installed package.
    p = builtin_workflow_path(w)
    if not p.is_file():
        raise CfgError(f"Unknown workflow: {w} (expected file: {p})")
    return p
