"""
Best-effort git sync for all repos listed in a host inventory entry.

Safety principles:
- Always fetch first.
- Never auto-merge; only fast-forward (ff-only) when clean and not diverged.
- If the working tree is dirty, skip pull/merge by default.

Structure:
- `_classify` is a pure, read-only classification of what a sync *would* do. It
  runs in both plan (dry-run) and live modes — in live mode it is called *after*
  the fetch so divergence reflects the post-fetch state.
- `_plan_result` renders a classification as a dry-run result (no mutations).
- `_apply_result` performs the resulting mutation (ff-merge / submodule update)
  and renders the live result.

Plan and live thus share one decision tree instead of maintaining two parallel ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from cfg.core.subprocess import run_cmd


@dataclass(frozen=True)
class RepoSyncResult:
    repo_id: str
    path: Path
    fetched: bool
    updated: bool
    message: str


def _git(repo: Path, args: list[str], *, check: bool = True) -> str:
    return run_cmd(["git", *args], cwd=repo, check=check)


def _is_git_repo(path: Path) -> bool:
    out = _git(path, ["rev-parse", "--is-inside-work-tree"], check=False)
    return out.strip() == "true"


def _is_dirty(path: Path) -> bool:
    out = _git(path, ["status", "--porcelain"], check=False)
    return bool(out.strip())


def _submodules_enabled(*, repo: Path, submodules: bool) -> bool:
    return bool(submodules and (repo / ".gitmodules").is_file())


def _precheck_repo(*, repo_id: str, repo: Path) -> RepoSyncResult | None:
    if not repo.exists():
        return RepoSyncResult(
            repo_id=repo_id, path=repo, fetched=False, updated=False, message="missing path"
        )
    if not repo.is_dir():
        return RepoSyncResult(
            repo_id=repo_id, path=repo, fetched=False, updated=False, message="not a directory"
        )
    if not _is_git_repo(repo):
        return RepoSyncResult(
            repo_id=repo_id, path=repo, fetched=False, updated=False, message="not a git repo"
        )
    return None


def _get_upstream(repo: Path) -> str:
    return _git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], check=False).strip()


def _get_divergence(repo: Path, upstream: str) -> tuple[int, int] | None:
    """
    Return (ahead, behind) counts vs upstream, or None if we can't parse.
    """
    counts = _git(repo, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"], check=False).strip()
    try:
        a, b = counts.split()
        return int(a), int(b)
    except ValueError:
        return None


class _Outcome(Enum):
    FETCH_ONLY = auto()
    DIRTY = auto()
    NO_UPSTREAM = auto()
    UNKNOWN = auto()
    UP_TO_DATE = auto()
    NOT_FF = auto()
    FAST_FORWARD = auto()


@dataclass(frozen=True)
class _Plan:
    outcome: _Outcome
    upstream: str = ""
    ahead: int = 0
    behind: int = 0
    # Whether a submodule update is applicable (requested AND .gitmodules present).
    submodules: bool = False


def _classify(repo: Path, *, fetch_only: bool, allow_dirty: bool, submodules: bool) -> _Plan:
    """
    Read-only classification of what a sync would do.

    In live mode this must be called *after* the fetch, so divergence reflects
    the freshly-updated remote-tracking ref.
    """
    if fetch_only:
        return _Plan(_Outcome.FETCH_ONLY, submodules=_submodules_enabled(repo=repo, submodules=submodules))

    if _is_dirty(repo) and not allow_dirty:
        return _Plan(_Outcome.DIRTY)

    upstream = _get_upstream(repo)
    if not upstream:
        return _Plan(_Outcome.NO_UPSTREAM)

    div = _get_divergence(repo, upstream)
    if div is None:
        return _Plan(
            _Outcome.UNKNOWN,
            upstream=upstream,
            submodules=_submodules_enabled(repo=repo, submodules=submodules),
        )

    ahead, behind = div
    sub = _submodules_enabled(repo=repo, submodules=submodules)
    if behind == 0:
        return _Plan(_Outcome.UP_TO_DATE, upstream=upstream, ahead=ahead, behind=behind, submodules=sub)
    if ahead != 0:
        return _Plan(_Outcome.NOT_FF, upstream=upstream, ahead=ahead, behind=behind)
    return _Plan(_Outcome.FAST_FORWARD, upstream=upstream, ahead=ahead, behind=behind, submodules=sub)


def _plan_result(*, repo_id: str, repo: Path, plan: _Plan) -> RepoSyncResult:
    """Render a classification as a plan-mode result (no mutating git commands run)."""
    sub = " (and update submodules)" if plan.submodules else ""
    o = plan.outcome

    if o is _Outcome.DIRTY:
        message = "dry-run: dirty; would fetch only (skip pull) (no fetch performed in plan mode)"
    elif o is _Outcome.NO_UPSTREAM:
        message = "dry-run: no upstream; would fetch only (no fetch performed in plan mode)"
    elif o is _Outcome.NOT_FF:
        message = (
            f"dry-run: not ff-only (ahead={plan.ahead}, behind={plan.behind}); would fetch only "
            "(no fetch performed in plan mode)"
        )
    elif o is _Outcome.FAST_FORWARD:
        message = f"dry-run: would fast-forward{sub} (no fetch/merge performed in plan mode)"
    else:  # FETCH_ONLY, UNKNOWN, UP_TO_DATE all reduce to "would fetch"
        message = f"dry-run: would fetch{sub} (no fetch performed in plan mode)"

    return RepoSyncResult(
        repo_id=repo_id,
        path=repo,
        fetched=True,
        updated=o is _Outcome.FAST_FORWARD,
        message=message,
    )


def _update_submodules(repo: Path, plan: _Plan) -> bool:
    if not plan.submodules:
        return False
    _git(repo, ["submodule", "update", "--init", "--recursive"], check=True)
    return True


def _apply_result(*, repo_id: str, repo: Path, plan: _Plan) -> RepoSyncResult:
    """Perform the mutation implied by `plan` (the fetch already ran) and render the result."""
    o = plan.outcome

    if o is _Outcome.DIRTY:
        message = "dirty; skipped pull"
    elif o is _Outcome.NO_UPSTREAM:
        message = "no upstream; fetched only"
    elif o is _Outcome.UNKNOWN:
        message = "unknown divergence; fetched only"
    elif o is _Outcome.NOT_FF:
        message = f"not ff-only (ahead={plan.ahead}, behind={plan.behind}); fetched only"
    elif o is _Outcome.FAST_FORWARD:
        _git(repo, ["merge", "--ff-only", plan.upstream], check=True)
        updated_sub = _update_submodules(repo, plan)
        message = "fast-forwarded (submodules updated)" if updated_sub else "fast-forwarded"
        return RepoSyncResult(repo_id=repo_id, path=repo, fetched=True, updated=True, message=message)
    else:  # FETCH_ONLY or UP_TO_DATE: maybe update submodules, never merge
        updated_sub = _update_submodules(repo, plan)
        if o is _Outcome.FETCH_ONLY:
            message = "fetched (submodules updated)" if updated_sub else "fetched"
        else:
            message = "up-to-date (submodules updated)" if updated_sub else "up-to-date"

    return RepoSyncResult(repo_id=repo_id, path=repo, fetched=True, updated=False, message=message)


def sync_repo(
    *,
    repo_id: str,
    path: Path,
    remote: str = "origin",
    fetch_only: bool = False,
    allow_dirty: bool = False,
    submodules: bool = False,
    dry_run: bool = False,
) -> RepoSyncResult:
    """
    Sync a single git repo checkout.

    Behavior:
    - `git fetch <remote> --prune --tags`
    - if fetch_only: stop after fetch
    - if dirty and not allow_dirty: skip merge/pull
    - if upstream exists: ff-only merge from @{u} when behind-only
    """
    repo = Path(path).expanduser().resolve()

    precheck = _precheck_repo(repo_id=repo_id, repo=repo)
    if precheck is not None:
        return precheck

    if dry_run:
        # Plan mode: classify from the current (pre-fetch) state; run no mutating git commands.
        plan = _classify(repo, fetch_only=fetch_only, allow_dirty=allow_dirty, submodules=submodules)
        return _plan_result(repo_id=repo_id, repo=repo, plan=plan)

    _git(repo, ["fetch", remote, "--prune", "--tags"], check=True)
    # Classify from the post-fetch state, then perform the implied mutation.
    plan = _classify(repo, fetch_only=fetch_only, allow_dirty=allow_dirty, submodules=submodules)
    return _apply_result(repo_id=repo_id, repo=repo, plan=plan)
