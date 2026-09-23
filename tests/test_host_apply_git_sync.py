from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.host.apply_git_sync import sync_apply_root

if TYPE_CHECKING:
    from pathlib import Path


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", content)


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path, Path]:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    local = tmp_path / "local"
    git(tmp_path, "clone", str(remote), str(local))
    git(local, "checkout", "-b", "main")
    commit(local, "base", "base")
    git(local, "push", "-u", "origin", "main")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-b", "main", str(remote), str(other))
    return remote, local, other


def test_apply_sync_fast_forwards_before_apply(repos: tuple[Path, Path, Path]) -> None:
    _, local, other = repos
    commit(other, "remote", "remote")
    git(other, "push")
    assert sync_apply_root(local, dry_run=False) == "fast-forwarded"
    assert (local / "remote").read_text(encoding="utf-8") == "remote"


def test_apply_sync_rebases_and_pushes_clean_divergence(repos: tuple[Path, Path, Path]) -> None:
    remote, local, other = repos
    commit(local, "local", "local")
    commit(other, "remote", "remote")
    git(other, "push")
    assert sync_apply_root(local, dry_run=False) == "rebased and pushed"
    assert git(local, "rev-parse", "HEAD") == git(remote, "rev-parse", "refs/heads/main")
    assert (local / "remote").exists()


def test_apply_sync_pushes_ahead_only(repos: tuple[Path, Path, Path]) -> None:
    remote, local, _ = repos
    commit(local, "local", "local")
    assert sync_apply_root(local, dry_run=False) == "pushed"
    assert git(local, "rev-parse", "HEAD") == git(remote, "rev-parse", "refs/heads/main")


def test_apply_sync_conflict_keeps_checkout_unchanged(repos: tuple[Path, Path, Path]) -> None:
    _, local, other = repos
    commit(local, "same", "local")
    before = git(local, "rev-parse", "HEAD")
    commit(other, "same", "remote")
    git(other, "push")
    with pytest.raises(CfgError, match="conflict"):
        sync_apply_root(local, dry_run=False)
    assert git(local, "rev-parse", "HEAD") == before
    assert git(local, "status", "--porcelain") == ""


def test_apply_sync_dirty_fails_before_fetch(repos: tuple[Path, Path, Path]) -> None:
    _, local, other = repos
    commit(other, "remote", "remote")
    git(other, "push")
    (local / "untracked").write_text("dirty", encoding="utf-8")
    with pytest.raises(CfgError, match="dirty"):
        sync_apply_root(local, dry_run=False)
    assert git(local, "rev-parse", "origin/main") != git(other, "rev-parse", "HEAD")


def test_apply_sync_unfinished_git_operation_fails(repos: tuple[Path, Path, Path]) -> None:
    _, local, _ = repos
    (local / git(local, "rev-parse", "--git-path", "rebase-merge")).mkdir()
    with pytest.raises(CfgError, match="unfinished Git operation"):
        sync_apply_root(local, dry_run=False)


def test_apply_sync_dry_run_does_not_fetch(repos: tuple[Path, Path, Path]) -> None:
    _, local, other = repos
    commit(other, "remote", "remote")
    git(other, "push")
    assert sync_apply_root(local, dry_run=True) == "dry-run: would fetch and check sync"
    assert git(local, "rev-parse", "origin/main") != git(other, "rev-parse", "HEAD")
