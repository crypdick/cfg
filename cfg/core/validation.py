"""Read-only validation of a complete personalization repository."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cfg.core.deploy_discovery import discover_host_deploy
from cfg.core.errors import CfgError
from cfg.core.ids import OwnerId
from cfg.core.inventory import load_inventory
from cfg.core.owners import (
    load_owner_manifest_index,
    owner_id_to_dir,
    owner_scope,
    resolve_host_owner_ids_for_host,
)
from cfg.core.scope import Scope
from cfg.host.managed_home import resolve_host_home_plan
from cfg.render.generated import render_template_write_to_string
from cfg.repo.cli_common import resolved_repo_owner_ids
from cfg.repo.plan import resolve_repo_outputs


@dataclass(frozen=True, slots=True)
class ValidationReport:
    hosts: int
    repos: int
    owners: int

    def lines(self) -> list[str]:
        return [
            "ok: configuration is valid",
            f"hosts: {self.hosts}",
            f"repos: {self.repos}",
            f"owners: {self.owners}",
        ]


def _validate_deploy_entrypoints(
    *,
    cfg_root: Path,
    owner_ids: Sequence[OwnerId],
) -> None:
    for owner_id in owner_ids:
        deploy_path = owner_id_to_dir(cfg_root, owner_id) / "deploy.py"
        if not deploy_path.is_file():
            continue
        if discover_host_deploy(cfg_root, owner_id) is None:
            raise CfgError(f"Host deploy must define callable main(): {deploy_path}")


def validate_configuration(cfg_root: Path) -> ValidationReport:
    """Parse and resolve every configured host, repo, output, and deploy."""
    inventory = load_inventory(cfg_root)
    manifest_index = load_owner_manifest_index(cfg_root)

    host_owner_ids = [owner_id for owner_id in manifest_index if owner_scope(owner_id) is Scope.HOST]
    _validate_deploy_entrypoints(
        cfg_root=cfg_root,
        owner_ids=host_owner_ids,
    )

    for owner_id, manifest in manifest_index.items():
        for rel in manifest.generated:
            template_path = (
                owner_id_to_dir(cfg_root, owner_id) / "render" / "templates" / f"{rel.as_posix()}.j2"
            )
            if not template_path.is_file():
                raise CfgError(f"Missing generated template source: {template_path}")

    for repo_id, repo_loaded in sorted(inventory.repos.items()):
        owner_ids = resolved_repo_owner_ids(
            cfg_root=cfg_root,
            cfg=repo_loaded.settings,
        )
        outputs = resolve_repo_outputs(
            cfg_root=cfg_root,
            repo_id=repo_id,
            enabled_owner_ids=owner_ids,
            path_provider_overrides=repo_loaded.settings.path_provider_overrides,
        )
        for write in outputs.generated:
            render_template_write_to_string(write)

    for _host_name, host_loaded in sorted(inventory.hosts.items()):
        owner_ids = resolve_host_owner_ids_for_host(
            cfg_root=cfg_root,
            cfg_inventory=inventory,
            host_settings=host_loaded.settings,
        )
        resolve_host_home_plan(
            cfg_root=cfg_root,
            host=host_loaded.settings.name,
            enabled_owner_ids=owner_ids,
        )

    return ValidationReport(
        hosts=len(inventory.hosts),
        repos=len(inventory.repos),
        owners=len(manifest_index),
    )
