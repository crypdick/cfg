from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.host.cli_common import host_ctx, require_registered_host
from cfg.host.sync_repos import sync_repo


def sync_repos(
    *,
    host: str | None,
    fetch_only: bool,
    remote: str,
    allow_dirty: bool,
    submodules: bool,
    dry_run: bool,
) -> list[str]:
    """Business logic for `cfg host sync-repos` (returns lines to print)."""
    ctx, host = host_ctx(host)
    entry = require_registered_host(ctx, host)

    repos = dict(entry.repos or {})
    if not repos:
        return ["(no repos configured for host)"]

    failures: list[str] = []
    fetched = 0
    updated = 0

    lines: list[str] = []
    for repo_id, repo_path in sorted(repos.items(), key=lambda kv: kv[0]):
        try:
            res = sync_repo(
                repo_id=repo_id,
                path=Path(repo_path),
                remote=remote,
                fetch_only=fetch_only,
                allow_dirty=allow_dirty,
                submodules=submodules,
                dry_run=dry_run,
            )
            if res.fetched:
                fetched += 1
            if res.updated:
                updated += 1
            lines.append(f"{repo_id}: {res.message} ({res.path})")
        except Exception as e:  # noqa: BLE001  # allow: exception-handling -- report batch at end
            failures.append(f"{repo_id}: {e}")
            lines.append(f"{repo_id}: ERROR: {e}")

    lines.append("")
    # In plan mode the counts are projections ("would fetch / would update"), not actions taken.
    fetch_label, update_label = ("would-fetch", "would-update") if dry_run else ("fetched", "updated")
    lines.append(
        f"summary: repos={len(repos)} {fetch_label}={fetched} {update_label}={updated} failed={len(failures)}"
    )
    if failures:
        msg = "\n".join(f"- {f}" for f in failures)
        raise CfgError(f"Some repos failed to sync:\n{msg}")
    return lines
