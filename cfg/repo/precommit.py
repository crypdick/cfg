from __future__ import annotations

from pathlib import Path

PRECOMMIT_PATH = Path(".pre-commit-config.yaml")


def read_repo_precommit(repo_root: Path) -> str | None:
    p = repo_root / PRECOMMIT_PATH
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8")


def write_repo_precommit(repo_root: Path, content: str) -> None:
    p = repo_root / PRECOMMIT_PATH
    p.write_text(content, encoding="utf-8")
