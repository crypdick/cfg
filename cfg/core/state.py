"""
Repo-local state stored inside each target repo at `.cfg/` (git-excluded).

Files:
- `.cfg/state.json`: structured state used for idempotency/undo tracking

This keeps repo-local mutations (like writing ignores)
private to the working tree and not committed to repo history.
"""

from __future__ import annotations

import json
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.models import RepoStateManifest

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
