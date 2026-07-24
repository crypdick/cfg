"""
Inventory loader.

Inventory lives as TOML in the personalization repository under:
  - host settings: `hosts/<host>/cfg.toml`
  - repo settings: `repos/<owner>/<repo>/cfg.toml`

Implementation notes:
- TOML is the source of truth; Pydantic is used for validation and typed access only.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cfg.core.errors import CfgError
from cfg.core.ids import HostName, RepoId, parse_host_name, parse_repo_id
from cfg.core.models import HostSettings, RepoSettings, safe_repo_id_path


@dataclass(frozen=True)
class Loaded[T]:
    settings: T
    source_path: Path


@dataclass(frozen=True)
class Inventory:
    repos: dict[str, Loaded[RepoSettings]]
    hosts: dict[str, Loaded[HostSettings]]

    def host_get(self, host_name: str) -> HostSettings | None:
        item = self.hosts.get(host_name)
        return item.settings if item else None


def _iter_settings_files(base_dir: Path, *, depth: int) -> list[Path]:
    """
    Find inventory settings files named `cfg.toml`.

    Each scope has its own settings root, so this only needs to ignore scratch
    directories and malformed nesting.
    """
    if not base_dir.is_dir():
        return []

    out: list[Path] = []
    for p in sorted(base_dir.rglob("cfg.toml")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(base_dir).parts
        if len(rel_parts) != depth or rel_parts[-1] != "cfg.toml":
            continue
        if any(part == "__pycache__" for part in rel_parts):
            continue
        # Ignore hidden/scratch entries at the top-level.
        #
        # - hosts: host names should not be dot/underscore prefixed.
        # - repos: allow dot-prefixed repo names (e.g. `owner/.cfg`) but still ignore
        #   dot/underscore owners (top-level segment).
        if rel_parts:
            top = rel_parts[0]
            if top.startswith(("_", ".")):
                continue
        out.append(p)
    return out


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise CfgError(f"Failed to read TOML inventory file: {path}\n{e}") from e

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        raise CfgError(f"Failed to parse TOML inventory file: {path}\n{e}") from e

    if not isinstance(data, dict):  # pyright: ignore[reportUnnecessaryIsInstance] — defensive guard; tested via monkeypatch
        raise CfgError(f"Invalid TOML inventory file (expected a table): {path}")
    return data


def _host_name_from_host_toml_path(*, hosts_dir: Path, path: Path) -> HostName:
    rel = path.resolve().relative_to(hosts_dir.resolve())
    if len(rel.parts) != 2 or rel.parts[1] != "cfg.toml":
        raise CfgError(f"Invalid host inventory TOML path (expected host/<host>/cfg.toml): {path}")
    return parse_host_name(rel.parts[0])


def _repo_id_from_repo_toml_path(*, repos_dir: Path, path: Path) -> RepoId:
    rel = path.resolve().relative_to(repos_dir.resolve())
    if len(rel.parts) == 3 and rel.parts[2] == "cfg.toml":
        owner, repo, _ = rel.parts
        rid = f"{owner}/{repo}"
    else:
        raise CfgError(f"Invalid repo inventory TOML path (expected repo/<owner>/<repo>/cfg.toml): {path}")
    # Validate shape early for nicer errors.
    try:
        safe_repo_id_path(rid)
    except ValueError as e:
        raise CfgError(f"Invalid repo id derived from TOML filename: {path}\n{e}") from e
    return parse_repo_id(rid)


def _load_host_from_toml(*, hosts_dir: Path, path: Path) -> HostSettings:
    inferred = _host_name_from_host_toml_path(hosts_dir=hosts_dir, path=path)
    data = _load_toml(path)

    name = str(data.get("name") or inferred).strip()
    if name != inferred:
        raise CfgError(f"Host TOML `name` must match filename stem ({inferred!r}): {path}")

    repos_raw = data.get("repos") or {}
    if not isinstance(repos_raw, dict):
        raise CfgError(f"Host TOML `repos` must be a table/dict: {path}")
    vars_raw = data.get("vars") or {}
    if not isinstance(vars_raw, dict):
        raise CfgError(f"Host TOML `vars` must be a table/dict: {path}")

    try:
        return HostSettings.model_validate({**data, "name": name})
    except (TypeError, ValueError) as e:
        raise CfgError(f"Invalid host inventory TOML content: {path}\n{e}") from e


def _load_repo_from_toml(*, repos_dir: Path, path: Path) -> RepoSettings:
    inferred = _repo_id_from_repo_toml_path(repos_dir=repos_dir, path=path)
    data = _load_toml(path)

    rid = str(data.get("id") or inferred).strip()
    if rid != inferred:
        raise CfgError(f"Repo TOML `id` must match its location/filename ({inferred!r}): {path}")

    settings_raw = data.get("settings")
    if settings_raw not in (None, {}):
        raise CfgError(f"Repo TOML `settings` is no longer supported (remove it): {path}")

    try:
        return RepoSettings.model_validate({**data, "id": rid})
    except (TypeError, ValueError) as e:
        raise CfgError(f"Invalid repo inventory TOML content: {path}\n{e}") from e


def load_inventory(cfg_root: Path) -> Inventory:
    """
    Load inventory from `hosts/**/cfg.toml` and `repos/**/cfg.toml`.
    """
    inventory_hosts = cfg_root / "hosts"
    inventory_repos = cfg_root / "repos"

    repos: dict[str, Loaded[RepoSettings]] = {}
    hosts: dict[str, Loaded[HostSettings]] = {}

    for p in _iter_settings_files(inventory_hosts, depth=2):
        hs = _load_host_from_toml(hosts_dir=inventory_hosts, path=p)
        existing_host = hosts.get(hs.name)
        if existing_host is not None:
            raise CfgError(
                f"Duplicate host name in inventory:\n- name: {hs.name}\n- {existing_host.source_path}\n- {p}\n"
            )
        hosts[hs.name] = Loaded(settings=hs, source_path=p)

    for p in _iter_settings_files(inventory_repos, depth=3):
        rs = _load_repo_from_toml(repos_dir=inventory_repos, path=p)
        existing_repo = repos.get(rs.id)
        if existing_repo is not None:
            raise CfgError(
                f"Duplicate repo id in inventory:\n- id: {rs.id}\n- {existing_repo.source_path}\n- {p}\n"
            )
        repos[rs.id] = Loaded(settings=rs, source_path=p)

    return Inventory(repos=repos, hosts=hosts)
