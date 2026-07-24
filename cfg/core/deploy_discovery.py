"""Deploy discovery for features."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path

from cfg.core.owners import feature_manifest_path


def discover_feature_deploy(cfg_root: Path, owner_id: str) -> Callable[[], None] | None:
    """
    Discover deploy function for an owner.

    Convention: <owner_dir>/deploy.py with main() function.
    Supports both feature deploys (host/feature/*) and host-specific deploys (host/<hostname>).
    Returns None if no deploy exists.
    """
    if not owner_id.startswith("host/"):
        return None

    if "/feature/" not in owner_id:
        return None
    manifest_path = feature_manifest_path(cfg_root, owner_id)
    if not manifest_path.exists():
        return None

    feature_dir = manifest_path.parent
    deploy_file = feature_dir / "deploy.py"

    if deploy_file.exists():
        deploy_name = owner_id.replace("/", "_")
        spec = importlib.util.spec_from_file_location(f"deploy_{deploy_name}", deploy_file)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "main"):
                return mod.main

    return None
