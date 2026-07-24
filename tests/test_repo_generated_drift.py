from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cfg.core.errors import CfgError
from cfg.core.models import RepoSettings
from cfg.repo import generated_drift as gd


def test_check_generated_file_drift_returns_early_when_staged_and_not_in_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["other.txt"])
    # If it doesn't early-return, we'd hit template rendering; guard by making that explode.
    monkeypatch.setattr(
        gd, "render_repo_generated_template_writes", lambda **_kw: (_ for _ in ()).throw(Exception("no"))
    )

    gd.check_generated_file_drift(
        cfg_root=tmp_path,
        repo_root=tmp_path,
        repo_id="o/r",
        repo_cfg=RepoSettings(id="o/r"),
        enabled_owner_ids=[],
        staged=True,
        rel=Path("target.txt"),
    )


def test_check_generated_file_drift_returns_early_when_no_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["target.txt"])
    monkeypatch.setattr(gd, "render_repo_generated_template_writes", lambda **_kw: [])

    gd.check_generated_file_drift(
        cfg_root=tmp_path,
        repo_root=tmp_path,
        repo_id="o/r",
        repo_cfg=RepoSettings(id="o/r"),
        enabled_owner_ids=[],
        staged=True,
        rel=Path("target.txt"),
    )


def test_expected_generated_content_errors_when_multiple_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _W:
        def __init__(self) -> None:
            self.data = {}

    monkeypatch.setattr(gd, "render_repo_generated_template_writes", lambda **_kw: [_W(), _W()])
    monkeypatch.setattr(gd, "render_template_write_to_string", lambda _w: "x")

    with pytest.raises(CfgError, match="Expected exactly one generated write"):
        gd._expected_generated_content(
            cfg_root=tmp_path,
            repo_id="o/r",
            enabled_owner_ids=[],
            path_provider_overrides=None,
            rel=Path("a.txt"),
        )


def test_check_generated_file_drift_staged_missing_content_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["gen.txt"])
    monkeypatch.setattr(
        gd, "render_repo_generated_template_writes", lambda **_kw: [type("W", (), {"data": {}})()]
    )
    monkeypatch.setattr(gd, "render_template_write_to_string", lambda _w: "expected\n")
    monkeypatch.setattr(gd, "staged_file_content", lambda _repo, _rel: None)

    gd.check_generated_file_drift(
        cfg_root=tmp_path,
        repo_root=tmp_path,
        repo_id="o/r",
        repo_cfg=RepoSettings(id="o/r"),
        enabled_owner_ids=[],
        staged=True,
        rel=Path("gen.txt"),
    )


def test_check_generated_file_drift_nonstaged_missing_file_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gd, "render_repo_generated_template_writes", lambda **_kw: [type("W", (), {"data": {}})()]
    )
    monkeypatch.setattr(gd, "render_template_write_to_string", lambda _w: "expected\n")

    gd.check_generated_file_drift(
        cfg_root=tmp_path,
        repo_root=tmp_path,
        repo_id="o/r",
        repo_cfg=RepoSettings(id="o/r"),
        enabled_owner_ids=[],
        staged=False,
        rel=Path("missing.txt"),
    )


def test_check_generated_file_drift_nonstaged_equal_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gd, "render_repo_generated_template_writes", lambda **_kw: [type("W", (), {"data": {}})()]
    )
    monkeypatch.setattr(gd, "render_template_write_to_string", lambda _w: "same\n")

    (tmp_path / "gen.txt").write_text("same\n", encoding="utf-8")
    gd.check_generated_file_drift(
        cfg_root=tmp_path,
        repo_root=tmp_path,
        repo_id="o/r",
        repo_cfg=RepoSettings(id="o/r"),
        enabled_owner_ids=[],
        staged=False,
        rel=Path("gen.txt"),
    )


def test_check_repo_precommit_drift_passes_precommit_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Path] = {}

    def fake_check(*, rel: Path, **_kw: Any) -> None:
        captured["rel"] = rel

    monkeypatch.setattr(gd, "check_generated_file_drift", fake_check)
    gd.check_repo_precommit_drift(
        cfg_root=tmp_path,
        repo_root=tmp_path,
        repo_id="o/r",
        repo_cfg=RepoSettings(id="o/r"),
        enabled_owner_ids=[],
        staged=False,
    )
    assert captured["rel"].as_posix() == ".pre-commit-config.yaml"


def test_check_generated_file_drift_raises_with_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force staged path match
    monkeypatch.setattr(gd, "staged_paths", lambda _repo: ["gen.txt"])

    class _Write:
        def __init__(self) -> None:
            self.data = {
                "fragment_files": [
                    {"rel_to_cfg_root": "repos/x/fragment1"},
                    {"rel_to_cfg_root": "repos/x/fragment2"},
                ]
            }

    monkeypatch.setattr(gd, "render_repo_generated_template_writes", lambda **_kw: [_Write()])
    monkeypatch.setattr(gd, "render_template_write_to_string", lambda _w: "expected\n")
    monkeypatch.setattr(gd, "staged_file_content", lambda _repo, _rel: "actual\n")

    with pytest.raises(CfgError) as e:
        gd.check_generated_file_drift(
            cfg_root=tmp_path,
            repo_root=tmp_path,
            repo_id="o/r",
            repo_cfg=RepoSettings(id="o/r"),
            enabled_owner_ids=["repo/feature/x"],
            staged=True,
            rel=Path("gen.txt"),
        )

    msg = str(e.value)
    assert "Managed generated file drift detected" in msg
    assert "repos/x/fragment1" in msg
    assert "Diff:" in msg
    assert "expected (gen.txt from cfg)" in msg
    assert "actual (gen.txt in repo)" in msg
