from __future__ import annotations

import shutil
from pathlib import Path

from cfg.core.cli_logic_utils import normalize_feature_name, parse_repo_kv
from cfg.core.context import CfgContext
from cfg.core.host_id import cfg_host_hint_file, find_cfg_host, set_cfg_host
from cfg.core.models import HostSettings
from cfg.core.scope import Scope
from cfg.host.fs import safe_host_slug


def init_host(*, host: str, dry_run: bool, features: list[str], repos: list[str]) -> list[str]:
    """Business logic for `cfg host init` (returns lines to print)."""
    host = safe_host_slug(host)
    ctx = CfgContext.load()

    loaded = ctx.store.get_host(host)
    base = loaded if loaded is not None else HostSettings(name=host)

    repos_map = dict(base.repos or {})
    for item in repos:
        raw = str(item).strip()
        if not raw:
            continue
        repo_id, repo_path = parse_repo_kv(raw)
        repos_map[repo_id] = repo_path

    merged_features = list(base.features) + [
        normalize_feature_name(t, Scope.HOST) for t in (features or []) if t
    ]
    updated = base.model_copy(update={"features": merged_features, "repos": repos_map})

    out_path = ctx.store.get_host_path(host)
    existed = out_path.is_file()
    if dry_run:
        return [
            ("would update: " if existed else "would create: ") + str(out_path),
            "would write: (local host hint file)",
        ]

    ctx.store.save_host(updated)
    lines = [("updated: " if existed else "created: ") + str(out_path)]

    hint = set_cfg_host(host)
    lines.append(f"wrote: {hint}")

    return lines


def drop_host(*, host: str, dry_run: bool = False) -> list[str]:
    """Business logic for `cfg host drop` (returns lines to print).

    Deletes a host's entire inventory directory (cfg.toml, deploy.py, overlay/, etc.).
    Idempotent: dropping an already-absent host succeeds with a message.
    """
    host = safe_host_slug(host)
    ctx = CfgContext.load()

    host_dir = ctx.store.get_host_path(host).parent
    if not host_dir.is_dir():
        return [f"ok (not found): {host}"]

    if dry_run:
        return [f"would delete: {host_dir}"]

    shutil.rmtree(host_dir)
    ctx.store.reload()
    lines = [f"deleted: {host_dir}"]

    if find_cfg_host() == host:
        hint = cfg_host_hint_file()
        hint.unlink(missing_ok=True)
        lines.append(f"cleared: {hint} (was current host)")

    return lines


def edit_host(*, host: str) -> Path:
    """Business logic for `cfg host edit`."""
    ctx = CfgContext.load()
    return ctx.store.get_host_path(host)
