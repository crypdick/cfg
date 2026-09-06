"""Deploy discovery for host-scoped owners."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

from cfg.core.owners import FeatureOwner, HostOwner, owner_id_to_dir, parse_owner_ref
from cfg.core.scope import Scope


def discover_host_deploy(
    cfg_root: Path,
    owner_id: str,
    *,
    filename: Literal["deploy.py", "prepare.py"] = "deploy.py",
) -> Callable[[], None] | None:
    """
    Discover deploy function for an owner.

    Convention: <owner_dir>/{deploy,prepare}.py with main() function.
    NOTE: docs/pyinfra-idioms.md, Source preparation describes the phase contract.
    Supports both feature deploys (host/feature/*) and host-specific deploys (host/<hostname>).
    Returns None if no deploy exists.
    """
    try:
        owner = parse_owner_ref(owner_id)
    except ValueError:
        return None

    if isinstance(owner, FeatureOwner) and owner.scope is not Scope.HOST:
        return None
    if not isinstance(owner, (FeatureOwner, HostOwner)):
        return None

    owner_dir = owner_id_to_dir(cfg_root, owner.id)
    deploy_file = owner_dir / filename

    if deploy_file.exists():
        deploy_name = owner.id.replace("/", "_")
        spec = importlib.util.spec_from_file_location(f"deploy_{deploy_name}", deploy_file)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            candidate = getattr(mod, "main", None)
            if callable(candidate):
                return cast(Callable[[], None], candidate)

    return None
