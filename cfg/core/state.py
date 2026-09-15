"""Persistent ownership state for repo and host targets.

Files:
- `.cfg/state.json`: structured state used for idempotency/undo tracking
- `$XDG_CONFIG_HOME/cfg/state.json`: last successful host apply

State stays local to each target rather than duplicating desired configuration
inside the personalization repository.
"""

from __future__ import annotations

import json
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.models import HostStateManifest, RepoStateManifest
from cfg.core.xdg import xdg_config_home

CFG_DIR_NAME = ".cfg"
STATE_FILE = "state.json"


def cfg_dir(repo_root: Path) -> Path:
    return repo_root / CFG_DIR_NAME


def state_path(repo_root: Path) -> Path:
    return cfg_dir(repo_root) / STATE_FILE


def read_repo_state(repo_root: Path) -> RepoStateManifest:
    p = state_path(repo_root)
    if not p.is_file():
        return RepoStateManifest()

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CfgError(f"Invalid JSON in {p}: {e}") from e
    return RepoStateManifest.model_validate(data)


def write_repo_state(repo_root: Path, state: RepoStateManifest) -> Path:
    d = cfg_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)

    p = state_path(repo_root)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True).rstrip() + "\n",
        encoding="utf-8",
    )
    tmp.replace(p)
    return p


def host_state_path() -> Path:
    return xdg_config_home() / "cfg" / STATE_FILE


def read_host_state() -> HostStateManifest:
    p = host_state_path()
    if not p.is_file():
        return HostStateManifest()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CfgError(f"Invalid JSON in {p}: {e}") from e
    return HostStateManifest.model_validate(data)


def write_host_state(state: HostStateManifest) -> Path:
    p = host_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True).rstrip() + "\n",
        encoding="utf-8",
    )
    tmp.replace(p)
    return p
