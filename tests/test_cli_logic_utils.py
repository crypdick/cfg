from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cfg.core import cli_logic_utils as u
from cfg.core import typer_utils
from cfg.core.scope import Scope


def test_normalize_feature_name_strips_host_name() -> None:
    assert u.normalize_feature_name(" desktop ", Scope.HOST) == "desktop"


def test_normalize_feature_name_strips_repo_name() -> None:
    assert u.normalize_feature_name(" desktop ", Scope.REPO) == "desktop"


def test_normalize_feature_name_rejects_full_prefix() -> None:
    with pytest.raises(ValueError, match="Use a short host feature name"):
        u.normalize_feature_name("host/feature/i3", Scope.HOST)
    with pytest.raises(ValueError, match="Use a short repo feature name"):
        u.normalize_feature_name("repo/feature/python", Scope.REPO)


def test_normalize_feature_name_errors_on_empty() -> None:
    with pytest.raises(ValueError, match="Feature cannot be empty"):
        u.normalize_feature_name("   ", Scope.HOST)


def test_normalize_feature_name_errors_on_underscore_prefix() -> None:
    with pytest.raises(ValueError, match="Feature cannot start with '_'"):
        u.normalize_feature_name("_hidden", Scope.HOST)


def test_format_features_list() -> None:
    assert u.format_features_list(["a", "b"]) == ["features:", "- a", "- b"]


@dataclass(frozen=True)
class _TF:
    owner: str
    src: Path


def test_format_sourced_paths_list_empty_returns_empty_list() -> None:
    assert u.format_sourced_paths_list(header="publish_files", desired={}) == []


def test_format_sourced_paths_list_with_header_and_sorted() -> None:
    desired = {
        Path("b.txt"): _TF(owner="o2", src=Path("/tmp/b")),
        Path("a.txt"): _TF(owner="o1", src=Path("/tmp/a")),
    }
    assert u.format_sourced_paths_list(header="publish_files", desired=desired) == [
        "publish_files:",
        "- a.txt  (from o1: /tmp/a)",
        "- b.txt  (from o2: /tmp/b)",
    ]


def test_format_sourced_paths_list_no_header() -> None:
    desired = {Path("x"): _TF(owner="o", src=Path("/tmp/x"))}
    assert u.format_sourced_paths_list(header="", desired=desired) == [
        "- x  (from o: /tmp/x)",
    ]


def test_parse_repo_kv_ok(tmp_path: Path) -> None:
    repo_id, repo_path = u.parse_repo_kv(f"owner/repo={tmp_path}")
    assert repo_id == "owner/repo"
    assert repo_path == tmp_path.resolve()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "owner/repo",  # missing '='
        "owner/repo=",  # empty path
        "= /tmp/x",  # empty repo id
        " = ",  # empty both
    ],
)
def test_parse_repo_kv_invalid_raises_stable_message(raw: str) -> None:
    with pytest.raises(ValueError, match=r"Invalid --repo value \(expected 'owner/repo=/abs/path'\)"):
        u.parse_repo_kv(raw)


def test_echo_lines_calls_typer_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    out: list[str] = []

    def fake_echo(s: str, **_kw: Any) -> None:
        out.append(s)

    monkeypatch.setattr(typer_utils.typer, "echo", fake_echo)
    typer_utils.echo_lines(["a", "b"])
    assert out == ["a", "b"]
