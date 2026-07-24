"""
Public “host CLI business logic” API surface.

This exists so `cfg.host.app` can import a single module as `logic` without
breaking `import cfg.host.logic.<submodule>` (re-exporting names in
`cfg.host.logic.__init__` would shadow same-named submodules like `apply`).
"""

from __future__ import annotations

from cfg.host.logic.apply import apply
from cfg.host.logic.current import current_host
from cfg.host.logic.debug_inventory import debug_inventory
from cfg.host.logic.features import (
    features_add,
    features_create,
    features_delete,
    features_list,
    features_remove,
)
from cfg.host.logic.init import edit_host, init_host
from cfg.host.logic.managed import managed
from cfg.host.logic.mirror import add_path, remove_path
from cfg.host.logic.settings import settings
from cfg.host.logic.sync_repos import sync_repos
from cfg.host.logic.upgrade import upgrade
from cfg.host.logic.workflows import run_workflow

__all__ = [
    "add_path",
    "apply",
    "current_host",
    "debug_inventory",
    "edit_host",
    "features_add",
    "features_create",
    "features_delete",
    "features_list",
    "features_remove",
    "init_host",
    "managed",
    "remove_path",
    "run_workflow",
    "settings",
    "sync_repos",
    "upgrade",
]
