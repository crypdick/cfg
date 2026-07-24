"""
Public “repo CLI business logic” API surface.

This exists so `cfg.repo.app` can import a single module as `logic` without
breaking `import cfg.repo.logic.<submodule>` (re-exporting names in
`cfg.repo.logic.__init__` would shadow same-named submodules like `apply`).
"""

from __future__ import annotations

from cfg.repo.logic.apply import apply
from cfg.repo.logic.check import check
from cfg.repo.logic.features import features_add, features_list, features_remove
from cfg.repo.logic.init import edit_repo, init_repo
from cfg.repo.logic.linking import link, unlink
from cfg.repo.logic.mirror import add_path, remove_path
from cfg.repo.logic.settings import settings

__all__ = [
    "add_path",
    "apply",
    "check",
    "edit_repo",
    "features_add",
    "features_list",
    "features_remove",
    "init_repo",
    "link",
    "remove_path",
    "settings",
    "unlink",
]
