from __future__ import annotations

from typing import TYPE_CHECKING

from cfg.repo.precommit import read_repo_precommit, write_repo_precommit

if TYPE_CHECKING:
    from pathlib import Path


def test_read_write_repo_precommit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert read_repo_precommit(repo) is None

    write_repo_precommit(repo, "hello\n")
    assert read_repo_precommit(repo) == "hello\n"
