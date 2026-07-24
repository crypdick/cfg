"""Run deploys for all enabled features automatically."""

from __future__ import annotations

from pyinfra.api.deploy import deploy
from pyinfra.context import host

from cfg.core.deploy_discovery import discover_feature_deploy
from cfg.deploys.host_data import CFG_HOST_OWNER_IDS, cfg_root_from_host_data


@deploy("host: run feature deploys")
def deploy_features() -> None:
    """Auto-discover and run deploys for all enabled features (in dependency order)."""
    cfg_root = cfg_root_from_host_data()
    owner_ids = host.data.get(CFG_HOST_OWNER_IDS) or []

    for owner_id in owner_ids:
        deploy_fn = discover_feature_deploy(cfg_root, owner_id)
        if deploy_fn:
            deploy_fn()
