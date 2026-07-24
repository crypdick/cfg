from __future__ import annotations

from pathlib import Path

from cfg.core.inventory import load_inventory
from cfg.core.owners import load_owner_manifest_index, resolve_host_owner_ids_for_host


def test_example_personalization_repository_is_valid() -> None:
    root = Path(__file__).resolve().parents[1] / "examples" / "personalization"

    inventory = load_inventory(root)
    manifests = load_owner_manifest_index(root)
    host = inventory.host_get("workstation")

    assert host is not None
    assert "repo/example/demo" in manifests
    assert resolve_host_owner_ids_for_host(
        cfg_root=root,
        cfg_inventory=inventory,
        host_settings=host,
    ) == ["host/workstation", "host/feature/base", "host/feature/shell"]
