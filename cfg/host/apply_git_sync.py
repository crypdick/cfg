"""Synchronize the personalization checkout before a host apply."""

from __future__ import annotations

import tempfile
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.subprocess import run_cmd


def _git(root: Path, *args: str) -> str:
    return run_cmd(["git", *args], cwd=root)


def _trial_rebase(root: Path, upstream_oid: str) -> None:
    with tempfile.TemporaryDirectory(prefix="cfg-apply-rebase-") as temp:
        trial = Path(temp) / "worktree"
        _git(root, "worktree", "add", "--detach", str(trial), "HEAD")
        try:
            try:
                _git(trial, "rebase", "--no-autostash", upstream_oid)
            except CfgError as error:
                raise CfgError(
                    "Personalization repo rebase would conflict or fail.\n" + str(error)
                ) from error
        finally:
            _git(root, "worktree", "remove", "--force", str(trial))


def _upstream(root: Path) -> tuple[str, str, str]:
    if _git(root, "rev-parse", "--show-toplevel") != str(root.resolve()):
        raise CfgError("Personalization root must be the Git checkout root.")
    if _git(root, "status", "--porcelain", "--untracked-files=all"):
        raise CfgError("Personalization repo is dirty. Commit or discard changes.")
    for operation in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if (root / _git(root, "rev-parse", "--git-path", operation)).exists():
            raise CfgError(f"Personalization repo has an unfinished Git operation ({operation}).")
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    remote, remote_ref = _git(
        root, "for-each-ref", "--format=%(upstream:remotename)|%(upstream:remoteref)", f"refs/heads/{branch}"
    ).split("|", 1)
    if not remote or not remote_ref.startswith("refs/heads/"):
        raise CfgError("Personalization branch needs a remote upstream. Set one.")
    return upstream, remote, remote_ref


def _sync(root: Path, *, dry_run: bool) -> str:
    upstream, remote, remote_ref = _upstream(root)
    if dry_run:
        return "dry-run: would fetch and check sync"
    _git(root, "fetch", remote, "--prune")
    head = _git(root, "rev-parse", "HEAD")
    upstream_oid = _git(root, "rev-parse", upstream)
    ahead, behind = map(
        int, _git(root, "rev-list", "--left-right", "--count", f"{head}...{upstream_oid}").split()
    )
    if ahead and behind:
        _trial_rebase(root, upstream_oid)
        try:
            _git(root, "rebase", "--no-autostash", upstream_oid)
        except CfgError as error:
            run_cmd(["git", "rebase", "--abort"], cwd=root, check=False)
            raise CfgError(f"Personalization repo rebase failed.\n{error}") from error
    elif behind:
        _git(root, "merge", "--ff-only", upstream_oid)
    if ahead:
        _git(root, "push", remote, f"HEAD:{remote_ref}")
    if ahead and behind:
        return "rebased and pushed"
    if behind:
        return "fast-forwarded"
    if ahead:
        return "pushed"
    return "up-to-date"


def sync_apply_root(root: Path, *, dry_run: bool) -> str:
    """Fetch, safely integrate, and push the current branch's configured upstream."""
    try:
        return _sync(root, dry_run=dry_run)
    except CfgError as error:
        raise CfgError(
            f"Cannot sync personalization repo: {error}\nFix it, then rerun `cfg host apply`."
        ) from error
