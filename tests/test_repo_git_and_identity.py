from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cfg.repo import git as gitmod
from cfg.repo import identity as idmod

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_normalize_repo_id_common_formats() -> None:
    assert idmod.normalize_repo_id("git@github.com:owner/repo.git") == "owner/repo"
    assert idmod.normalize_repo_id("ssh://git@github.com/owner/repo.git") == "owner/repo"
    assert idmod.normalize_repo_id("https://github.com/owner/repo.git") == "owner/repo"
    assert idmod.normalize_repo_id("github.com/owner/repo") == "owner/repo"
    assert idmod.normalize_repo_id("owner/repo") == "owner/repo"
    assert idmod.normalize_repo_id("owner/repo/") == "owner/repo"


def test_repo_id_for_repo_prefers_origin_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(idmod, "origin_url", lambda _root: "git@github.com:a/b.git")
    assert idmod.repo_id_for_repo(tmp_path) == "a/b"


def test_repo_id_for_repo_returns_none_without_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(idmod, "origin_url", lambda _root: None)
    assert idmod.repo_id_for_repo(tmp_path) is None


def test_git_dir_dotgit_dir(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    assert gitmod.git_dir(repo) == (repo / ".git").resolve()


def test_git_dir_dotgit_file_gitdir_pointer(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: .git/worktrees/w1\n", encoding="utf-8")
    # can point to a path that doesn't exist; resolver still returns the resolved path
    assert gitmod.git_dir(repo) == (repo / ".git" / "worktrees" / "w1").resolve()


def test_git_dir_falls_back_to_git_rev_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    # no .git file/dir, so it will call run_cmd
    monkeypatch.setattr(gitmod, "run_cmd", lambda _cmd, **_kw: ".git")
    assert gitmod.git_dir(repo) == (repo / ".git").resolve()


def test_staged_paths_and_content_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run_cmd(cmd: list[str], **_kw: Any) -> str:
        if cmd[:3] == ["git", "diff", "--cached"]:
            return "a.txt\n\n b.txt \n"
        if cmd[:2] == ["git", "show"]:
            return "hello\n"
        raise AssertionError(f"unexpected cmd: {cmd}")

    monkeypatch.setattr(gitmod, "run_cmd", fake_run_cmd)
    assert gitmod.staged_paths(repo) == ["a.txt", "b.txt"]
    assert gitmod.staged_file_content(repo, "a.txt") == "hello\n"
