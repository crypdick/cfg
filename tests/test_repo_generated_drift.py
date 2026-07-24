from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.models import RepoSettings
from cfg.render.generated import TemplateWrite
from cfg.repo import generated_drift as gd

if TYPE_CHECKING:
    from collections.abc import Sequence


def _write(
    rel: str,
    content: str,
    *,
    fragments: Sequence[str] = (),
) -> TemplateWrite:
    return TemplateWrite(
        owner="repo/feature/test",
        rel=Path(rel),
        src=StringIO(content),
        data={"fragment_files": [{"rel_to_cfg_root": fragment} for fragment in fragments]},
        jinja_env_kwargs={},
    )


def _check(
    tmp_path: Path,
    *,
    staged: bool,
) -> None:
    gd.check_generated_files_drift(
        cfg_root=tmp_path,
        repo_root=tmp_path,
        repo_id="o/r",
        repo_cfg=RepoSettings(id="o/r"),
        enabled_owner_ids=[],
        staged=staged,
    )


def test_no_generated_writes_are_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gd, "render_repo_generated_template_writes", lambda **_kw: [])
    monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["unrelated.txt"])

    _check(tmp_path, staged=True)


def test_staged_check_ignores_unrelated_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gd,
        "render_repo_generated_template_writes",
        lambda **_kw: [_write("generated.txt", "expected\n")],
    )
    monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["unrelated.txt"])
    monkeypatch.setattr(
        gd,
        "staged_file_content",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected staged read")),
    )

    _check(tmp_path, staged=True)


def test_checks_every_generated_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gd,
        "render_repo_generated_template_writes",
        lambda **_kw: [
            _write("first.txt", "first\n"),
            _write("second.txt", "second\n"),
        ],
    )
    (tmp_path / "first.txt").write_text("first\n", encoding="utf-8")
    (tmp_path / "second.txt").write_text("second\n", encoding="utf-8")

    _check(tmp_path, staged=False)


@pytest.mark.parametrize("staged", [False, True])
def test_missing_generated_output_is_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    staged: bool,
) -> None:
    monkeypatch.setattr(
        gd,
        "render_repo_generated_template_writes",
        lambda **_kw: [_write("generated.txt", "expected\n")],
    )
    if staged:
        monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["generated.txt"])
        monkeypatch.setattr(gd, "staged_file_content", lambda _repo, _rel: None)

    with pytest.raises(CfgError, match="missing or staged for deletion"):
        _check(tmp_path, staged=staged)


def test_staged_empty_file_is_compared_not_treated_as_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gd,
        "render_repo_generated_template_writes",
        lambda **_kw: [_write("generated.txt", "expected\n")],
    )
    monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["generated.txt"])
    monkeypatch.setattr(gd, "staged_file_content", lambda _repo, _rel: "")

    with pytest.raises(CfgError) as error:
        _check(tmp_path, staged=True)

    assert "missing or staged for deletion" not in str(error.value)


def test_drift_error_names_fragments_and_includes_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gd,
        "render_repo_generated_template_writes",
        lambda **_kw: [
            _write(
                "generated.txt",
                "expected\n",
                fragments=("repos/x/fragment1", "repos/x/fragment2"),
            )
        ],
    )
    monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["generated.txt"])
    monkeypatch.setattr(gd, "staged_file_content", lambda _repo, _rel: "actual\n")

    with pytest.raises(CfgError) as error:
        _check(tmp_path, staged=True)

    message = str(error.value)
    assert "Managed generated file drift detected" in message
    assert "repos/x/fragment1" in message
    assert "Diff:" in message
    assert "expected (generated.txt from cfg)" in message
    assert "actual (generated.txt in repo)" in message
