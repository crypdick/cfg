from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.models import RepoStateManifest
from cfg.core.state import read_repo_state, write_repo_state

if TYPE_CHECKING:
    from pathlib import Path


def test_repo_state_read_write_and_invalid_json(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    st = read_repo_state(repo)
    assert isinstance(st, RepoStateManifest)

    out = write_repo_state(repo, RepoStateManifest())
    assert out.is_file()
    raw = out.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    # Validate it is valid JSON
    json.loads(raw)

    # Invalid json -> CfgError
    out.write_text("{", encoding="utf-8")
    with pytest.raises(CfgError, match="Invalid JSON"):
        read_repo_state(repo)
