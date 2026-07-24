from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from cfg.core.host_id import require_cfg_host
from cfg.core.root import require_cfg_root
from cfg.core.store import InventoryStore
from cfg.repo.identity import repo_id_for_repo


@dataclass
class CfgContext:
    root: Path
    store: InventoryStore

    # Lazy loaded
    _repo_root: Path | None = None
    _repo_id: str | None = None
    _host_name: str | None = None

    @classmethod
    def load(cls) -> CfgContext:
        root = require_cfg_root()
        return cls(
            root=root,
            store=InventoryStore(root),
        )

    @property
    def repo_root(self) -> Path | None:
        if self._repo_root is None:
            from cfg.repo.git import repo_root as find_repo_root

            try:
                self._repo_root = find_repo_root()
            except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
                return None
        return self._repo_root

    @property
    def repo_id(self) -> str | None:
        if self._repo_id is None and self.repo_root:
            self._repo_id = repo_id_for_repo(self.repo_root)
        return self._repo_id

    @property
    def host_name(self) -> str:
        if self._host_name is None:
            self._host_name = require_cfg_host()
        return self._host_name
