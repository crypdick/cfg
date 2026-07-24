from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cfg.host import sync_repos as sr

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_sync_repo_missing_or_not_dir(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    res = sr.sync_repo(repo_id="a/b", path=missing)
    assert res.message == "missing path"

    f = tmp_path / "file"
    f.write_text("x", encoding="utf-8")
    res2 = sr.sync_repo(repo_id="a/b", path=f)
    assert res2.message == "not a directory"


def test_sync_repo_not_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        assert argv[:2] == ["git", "rev-parse"]
        return "false\n"

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo)
    assert res.message == "not a git repo"


def test_sync_repo_fetch_only_with_submodules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitmodules").write_text("# x\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        calls.append(argv)
        if argv[0:2] != ["git", "rev-parse"]:
            return ""
        return "true\n"

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo, fetch_only=True, submodules=True)
    assert res.fetched is True
    assert res.updated is False
    assert res.message == "fetched (submodules updated)"
    assert ["git", "fetch", "origin", "--prune", "--tags"] in calls
    assert ["git", "submodule", "update", "--init", "--recursive"] in calls


def test_sync_repo_dirty_skips_pull(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        if argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if argv[:3] == ["git", "fetch", "origin"]:
            return ""
        if argv[:3] == ["git", "status", "--porcelain"]:
            return " M file\n"
        return ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo, allow_dirty=False)
    assert res.message == "dirty; skipped pull"


def test_sync_repo_no_upstream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        if argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if argv[:3] == ["git", "fetch", "origin"]:
            return ""
        if argv[:3] == ["git", "status", "--porcelain"]:
            return ""
        if argv[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return ""
        return ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo)
    assert res.message == "no upstream; fetched only"


def test_sync_repo_unknown_divergence_parse_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        if argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if argv[:3] == ["git", "fetch", "origin"]:
            return ""
        if argv[:3] == ["git", "status", "--porcelain"]:
            return ""
        if argv[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return "origin/main\n"
        if argv[:4] == ["git", "rev-list", "--left-right", "--count"]:
            return "nope\n"
        return ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo)
    assert res.message == "unknown divergence; fetched only"


def test_sync_repo_up_to_date_and_fast_forward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    # First scenario: behind=0 with submodules -> update submodules only.
    (repo / ".gitmodules").write_text("# x\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        calls.append(argv)
        if argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if argv[:3] == ["git", "fetch", "origin"]:
            return ""
        if argv[:3] == ["git", "status", "--porcelain"]:
            return ""
        if argv[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return "origin/main\n"
        if argv[:4] == ["git", "rev-list", "--left-right", "--count"]:
            return "0 0\n"
        if argv[:3] == ["git", "submodule", "update"]:
            return ""
        return ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo, submodules=True)
    assert res.message == "up-to-date (submodules updated)"
    assert ["git", "submodule", "update", "--init", "--recursive"] in calls

    # Second scenario: behind-only -> ff-only merge and no submodules.
    calls.clear()
    (repo / ".gitmodules").unlink()

    def fake_run_cmd2(argv: list[str], **_kw: Any) -> str:
        calls.append(argv)
        if argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if argv[:3] == ["git", "fetch", "origin"]:
            return ""
        if argv[:3] == ["git", "status", "--porcelain"]:
            return ""
        if argv[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return "origin/main\n"
        if argv[:4] == ["git", "rev-list", "--left-right", "--count"]:
            return "0 2\n"
        if argv[:3] == ["git", "merge", "--ff-only"]:
            return ""
        return ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd2)
    res2 = sr.sync_repo(repo_id="a/b", path=repo, submodules=False)
    assert res2.updated is True
    assert res2.message == "fast-forwarded"
    assert ["git", "merge", "--ff-only", "origin/main"] in calls


def test_sync_repo_diverged_or_ahead_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        if argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if argv[:3] == ["git", "fetch", "origin"]:
            return ""
        if argv[:3] == ["git", "status", "--porcelain"]:
            return ""
        if argv[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return "origin/main\n"
        if argv[:4] == ["git", "rev-list", "--left-right", "--count"]:
            return "1 2\n"
        return ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo)
    assert res.updated is False
    assert "not ff-only" in res.message


def test_sync_repo_fetch_only_no_submodules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        if argv[:2] == ["git", "rev-parse"]:
            return "true\n"
        return ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo, fetch_only=True, submodules=True)
    assert res.fetched is True
    assert res.updated is False
    # submodules requested but no .gitmodules present -> no submodule update, plain message
    assert res.message == "fetched"


def test_sync_repo_fast_forward_with_submodules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitmodules").write_text("# x\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        calls.append(argv)
        if argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if argv[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return "origin/main\n"
        if argv[:4] == ["git", "rev-list", "--left-right", "--count"]:
            return "0 2\n"
        return ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo, submodules=True)
    assert res.updated is True
    assert res.message == "fast-forwarded (submodules updated)"
    assert ["git", "merge", "--ff-only", "origin/main"] in calls
    assert ["git", "submodule", "update", "--init", "--recursive"] in calls


def _dry_fake(divergence: str = "0 0", *, upstream: str = "origin/main", dirty: str = ""):
    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        if argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if argv[:3] == ["git", "status", "--porcelain"]:
            return dirty
        if argv[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return upstream
        if argv[:4] == ["git", "rev-list", "--left-right", "--count"]:
            return divergence
        return ""

    return fake_run_cmd


def _assert_no_mutations(calls: list[list[str]]) -> None:
    for mutating in (["git", "fetch"], ["git", "merge"], ["git", "submodule"]):
        assert not any(c[: len(mutating)] == mutating for c in calls), f"plan mode ran {mutating}"


def test_sync_repo_dry_run_fetch_only_with_submodules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitmodules").write_text("# x\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        calls.append(argv)
        return "true\n" if argv[:2] == ["git", "rev-parse"] else ""

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo, fetch_only=True, submodules=True, dry_run=True)
    assert res.fetched is True
    assert res.updated is False
    assert res.message == "dry-run: would fetch (and update submodules) (no fetch performed in plan mode)"
    _assert_no_mutations(calls)


def test_sync_repo_dry_run_dirty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    calls: list[list[str]] = []

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        calls.append(argv)
        return _dry_fake(dirty=" M f\n")(argv)

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo, dry_run=True)
    assert res.message == "dry-run: dirty; would fetch only (skip pull) (no fetch performed in plan mode)"
    _assert_no_mutations(calls)


def test_sync_repo_dry_run_up_to_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(sr, "run_cmd", _dry_fake("0 0"))
    res = sr.sync_repo(repo_id="a/b", path=repo, dry_run=True)
    assert res.updated is False
    assert res.message == "dry-run: would fetch (no fetch performed in plan mode)"


def test_sync_repo_dry_run_fast_forward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    calls: list[list[str]] = []

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        calls.append(argv)
        return _dry_fake("0 2")(argv)

    monkeypatch.setattr(sr, "run_cmd", fake_run_cmd)
    res = sr.sync_repo(repo_id="a/b", path=repo, dry_run=True)
    assert res.updated is True
    assert res.message == "dry-run: would fast-forward (no fetch/merge performed in plan mode)"
    _assert_no_mutations(calls)


def test_sync_repo_dry_run_not_ff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(sr, "run_cmd", _dry_fake("1 2"))
    res = sr.sync_repo(repo_id="a/b", path=repo, dry_run=True)
    assert res.updated is False
    assert res.message == (
        "dry-run: not ff-only (ahead=1, behind=2); would fetch only (no fetch performed in plan mode)"
    )
