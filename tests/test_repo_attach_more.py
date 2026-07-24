from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cfg.repo.attach import attach_repo

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_attach_repo_writes_repo_id_from_origin_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = tmp_path / "cfg-root"
    cfg_root.mkdir(parents=True, exist_ok=True)

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".cfg").mkdir()
    (repo_root / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    (repo_root / ".git" / "info").mkdir(parents=True, exist_ok=True)

    import cfg.repo.attach as ra

    monkeypatch.setattr(ra, "git_dir", lambda _rr: repo_root / ".git")
    monkeypatch.setattr(ra, "git_config_get", lambda *_a, **_k: None)
    monkeypatch.setattr(ra, "origin_url", lambda *_a, **_k: "git@github.com:owner/repo.git")

    # Avoid invoking git in tests.
    monkeypatch.setattr(ra, "run_cmd", lambda *_a, **_k: "")

    attach_repo(repo_root=repo_root, cfg_root=cfg_root)

    # Repo identity is derived from git origin; we no longer persist `.cfg/repo_id`.
    assert not (repo_root / ".cfg" / "repo_id").exists()
    assert (repo_root / ".cfg" / "state.json").is_file()
    assert not (repo_root / ".git" / "hooks" / "pre-commit").exists()


def test_attach_repo_unsets_core_hooks_path_when_pointing_at_cfg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = tmp_path / "cfg-root"
    cfg_root.mkdir(parents=True, exist_ok=True)
    cfg_hooks_path = str((cfg_root / "hooks").resolve())

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    (repo_root / ".git" / "info").mkdir(parents=True, exist_ok=True)

    import cfg.repo.attach as ra

    monkeypatch.setattr(ra, "git_dir", lambda _rr: repo_root / ".git")
    monkeypatch.setattr(ra, "origin_url", lambda *_a, **_k: None)
    monkeypatch.setattr(ra, "git_config_get", lambda *_a, **_k: cfg_hooks_path)

    calls: list[list[str]] = []

    def fake_run_cmd(argv: list[str], **_kw: Any) -> str:
        calls.append(list(argv))
        return ""

    monkeypatch.setattr(ra, "run_cmd", fake_run_cmd)

    attach_repo(repo_root=repo_root, cfg_root=cfg_root)

    assert ["git", "config", "--local", "--unset-all", "core.hooksPath"] in calls


def test_attach_repo_removes_only_legacy_cfg_precommit_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = tmp_path / "cfg-root"
    cfg_root.mkdir()
    cfg_hook = (cfg_root / "hooks" / "pre-commit").resolve()

    repo_root = tmp_path / "repo"
    hook_path = repo_root / ".git" / "hooks" / "pre-commit"
    hook_path.parent.mkdir(parents=True)
    (repo_root / ".git" / "info").mkdir(parents=True)
    hook_path.write_text(f'#!/bin/sh\nexec "{cfg_hook}"\n', encoding="utf-8")

    import cfg.repo.attach as ra

    monkeypatch.setattr(ra, "git_dir", lambda _rr: repo_root / ".git")
    monkeypatch.setattr(ra, "origin_url", lambda *_a, **_k: None)
    monkeypatch.setattr(ra, "git_config_get", lambda *_a, **_k: None)

    attach_repo(repo_root=repo_root, cfg_root=cfg_root)
    assert not hook_path.exists()

    hook_path.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")
    attach_repo(repo_root=repo_root, cfg_root=cfg_root)
    assert hook_path.read_text(encoding="utf-8") == "#!/bin/sh\necho custom\n"
