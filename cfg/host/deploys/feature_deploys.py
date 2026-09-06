"""Run deploys for all enabled features automatically."""

from __future__ import annotations

from pyinfra.api.deploy import deploy

from cfg.core.deploy_discovery import discover_host_deploy
from cfg.deploys.host_data import cfg_root_from_host_data, owner_ids_from_host_data


@deploy("host: prepare feature sources")
def prepare_features() -> None:
    """Reconcile explicit sources for every enabled owner before package operations."""
    cfg_root = cfg_root_from_host_data()
    for owner_id in owner_ids_from_host_data():
        prepare_fn = discover_host_deploy(cfg_root, owner_id, filename="prepare.py")
        if prepare_fn:
            prepare_fn()


@deploy("host: run feature deploys")
def deploy_features() -> None:
    """Prepare all owners, then run their deploys in dependency order."""
    prepare_features()
    cfg_root = cfg_root_from_host_data()
    for owner_id in owner_ids_from_host_data():
        deploy_fn = discover_host_deploy(cfg_root, owner_id)
        if deploy_fn:
            deploy_fn()
