from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from cfg.core.errors import CfgError
from cfg.core.models import ManagedPathState, RepoStateManifest
from cfg.core.state import read_repo_state, write_repo_state

if TYPE_CHECKING:
    from pathlib import Path


def test_repo_state_read_write_and_invalid_json(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    st = read_repo_state(repo)
    assert isinstance(st, RepoStateManifest)

    state = RepoStateManifest(
        managed={
            "generated.txt": ManagedPathState(
                kind="generated",
                owner="repo/feature/test",
                digest="a" * 64,
                source="features/repo/test/render/templates/generated.txt.j2",
            )
        }
    )
    out = write_repo_state(repo, state)
    assert out.is_file()
    raw = out.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    # Validate it is valid JSON
    json.loads(raw)
    assert read_repo_state(repo) == state

    # Invalid json -> CfgError
    out.write_text("{", encoding="utf-8")
    with pytest.raises(CfgError, match="Invalid JSON"):
        read_repo_state(repo)


@pytest.mark.parametrize(
    ("path", "digest"),
    [
        ("../outside", "a" * 64),
        ("", "a" * 64),
        ("managed.txt", "not-a-digest"),
    ],
)
def test_repo_state_rejects_unsafe_managed_evidence(path: str, digest: str) -> None:
    with pytest.raises(ValidationError):
        RepoStateManifest(
            managed={
                path: ManagedPathState(
                    kind="mirror",
                    owner="repo/feature/test",
                    digest=digest,
                )
            }
        )
