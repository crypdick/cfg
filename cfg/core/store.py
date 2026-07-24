from __future__ import annotations

import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

import tomli_w

from cfg.core.inventory import Inventory, load_inventory
from cfg.core.models import HostSettings, RepoSettings, safe_repo_id_path
from cfg.core.scope import Scope
from cfg.host.fs import safe_host_slug

# Header comment added to all cfg-managed TOML files
_CFG_TOML_HEADER = """\
# Managed by cfg. Do not edit manually.
# Use `cfg host` or `cfg repo` commands to modify.

"""


def _atomic_write_toml(path: Path, data: dict[str, Any]) -> None:
    """Write a complete TOML document, then atomically publish it."""
    content = _CFG_TOML_HEADER + tomli_w.dumps(data)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            with suppress(FileNotFoundError):
                temporary_path.unlink()


class InventoryStore:
    def __init__(self, cfg_root: Path) -> None:
        self.cfg_root = cfg_root
        self._inventory: Inventory | None = None

    @property
    def inventory(self) -> Inventory:
        if self._inventory is None:
            self._inventory = load_inventory(self.cfg_root)
        return self._inventory

    def reload(self) -> None:
        self._inventory = None

    def get_repo(self, repo_id: str) -> RepoSettings | None:
        entry = self.inventory.repos.get(repo_id)
        return entry.settings if entry else None

    def get_repo_path(self, repo_id: str) -> Path:
        rel = safe_repo_id_path(repo_id)
        return Scope.REPO.settings_dir(self.cfg_root) / rel / "cfg.toml"

    def save_repo(self, settings: RepoSettings) -> Path:
        path = self.get_repo_path(settings.id)
        path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "id": settings.id,
            "features": list(settings.features),
        }
        if settings.origin_url is not None:
            data["origin_url"] = settings.origin_url
        if settings.alias is not None:
            data["alias"] = settings.alias
        if settings.path_provider_overrides:
            data["path_provider_overrides"] = dict(settings.path_provider_overrides)

        _atomic_write_toml(path, data)
        self.reload()  # Invalidate cache
        return path

    def get_host(self, host_name: str) -> HostSettings | None:
        entry = self.inventory.hosts.get(host_name)
        return entry.settings if entry else None

    def get_host_path(self, host_name: str) -> Path:
        slug = safe_host_slug(host_name)
        return Scope.HOST.settings_dir(self.cfg_root) / slug / "cfg.toml"

    def save_host(self, settings: HostSettings) -> Path:
        path = self.get_host_path(settings.name)
        path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "name": settings.name,
            "features": list(settings.features),
        }
        if settings.ssh is not None:
            data["ssh"] = settings.ssh.model_dump(exclude_none=True)
        if settings.repos:
            data["repos"] = {repo_id: str(path) for repo_id, path in settings.repos.items()}
        if settings.vars:
            data["vars"] = settings.vars

        _atomic_write_toml(path, data)
        self.reload()
        return path
