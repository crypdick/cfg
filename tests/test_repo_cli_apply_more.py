from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from typer.testing import CliRunner

from tests.test_repo_cli_more import _init_git_repo, _setup_cfg_root, _write

if TYPE_CHECKING:
    import pytest


def test_repo_init_dry_run_prints_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "init", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "would write:" in res.output
    assert "would attach repo." in res.output

    # Dry-run should not write inventory.
    repo_inv = cfg_root / "repos" / "owner" / "repo" / "cfg.toml"
    assert not repo_inv.exists()


def test_repo_check_returns_early_when_repo_not_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "check"])
    assert res.exit_code == 0


def test_repo_apply_refuses_when_dirty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Minimal repo inventory just so require_registered_repo passes.
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.apply as repo_apply_logic
    import main

    monkeypatch.setattr(repo_apply_logic, "resolved_repo_owner_ids", lambda **_kw: [])

    monkeypatch.setattr(repo_apply_logic, "run_cmd", lambda *_a, **_kw: " M x.py\n")

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "apply"])
    assert res.exit_code != 0
    assert res.exception is not None
    msg = str(res.exception)
    assert "Repo is dirty; refusing to apply managed files" in msg
    assert "git status --porcelain" in msg


def test_repo_apply_dry_run_prints_publish_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.apply as repo_apply_logic
    import main

    monkeypatch.setattr(repo_apply_logic, "resolved_repo_owner_ids", lambda **_kw: [])

    from cfg.repo.plan import CopyMirror, RepoApplyPlan

    source = cfg_root / "source.txt"
    _write(source, "a\n")
    plan = RepoApplyPlan(
        cfg_root=cfg_root,
        repo_root=repo_root,
        operations=(
            CopyMirror(
                owner="repo/feature/x",
                rel=Path("a.txt"),
                src=source,
            ),
        ),
    )
    monkeypatch.setattr(repo_apply_logic, "build_repo_apply_plan", lambda **_kw: plan)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "apply", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "would apply:" in res.output
    assert "mirror:" in res.output
    assert "a.txt" in res.output


def test_repo_settings_empty_prints_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.settings as repo_settings_logic
    import main

    monkeypatch.setattr(
        repo_settings_logic, "resolve_owner_files", lambda **_kw: type("_R", (), {"desired": {}})()
    )

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "settings"])
    assert res.exit_code == 0
    assert "linked:" in res.output
    assert "mirrored:" in res.output
    assert "generated:" in res.output


def test_repo_add_and_remove_paths_dry_run_and_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    _write(repo_root / "a.txt", "hello\n")
    monkeypatch.chdir(repo_root)

    import main

    # Mirror resolves the owner manifest path deterministically; owners need not exist on disk.
    runner = CliRunner()

    res = runner.invoke(main.app, ["repo", "mirror", "a.txt", "--dry-run"])
    assert res.exit_code == 0
    assert "would mirror:" in res.output

    res2 = runner.invoke(main.app, ["repo", "mirror", "a.txt"])
    assert res2.exit_code == 0, (res2.output, res2.exception)
    assert "added:" in res2.output

    # remove dry-run
    res3 = runner.invoke(main.app, ["repo", "unmirror", "a.txt", "--dry-run"])
    assert res3.exit_code == 0
    assert "would remove:" in res3.output

    # remove real
    res4 = runner.invoke(main.app, ["repo", "unmirror", "a.txt"])
    assert res4.exit_code == 0
    assert "removed:" in res4.output


def test_repo_apply_dry_run_skips_attach_and_passes_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Minimal repo inventory so require_registered_repo passes.
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.apply as repo_apply_logic
    import main

    # Dry-run must not mutate the repo by attaching.
    monkeypatch.setattr(
        repo_apply_logic,
        "attach_repo",
        lambda **_kw: (_ for _ in ()).throw(RuntimeError("attach_repo called")),
    )

    # Avoid depending on owner manifests for this test.
    monkeypatch.setattr(repo_apply_logic, "resolved_repo_owner_ids", lambda **_kw: [])

    from cfg.repo.plan import RepoApplyPlan

    called: dict[str, Any] = {}

    def fake_build_repo_apply_plan(**kw: Any) -> RepoApplyPlan:
        called.update(kw)
        return RepoApplyPlan(cfg_root=cfg_root, repo_root=repo_root, operations=())

    monkeypatch.setattr(repo_apply_logic, "build_repo_apply_plan", fake_build_repo_apply_plan)
    monkeypatch.setattr(
        repo_apply_logic,
        "apply_repo_plan",
        lambda _plan: (_ for _ in ()).throw(RuntimeError("apply_repo_plan called")),
    )

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "apply", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "skipping repo attachment step" in res.output
    assert called["repo_id"] == "owner/repo"


def test_repo_apply_installs_precommit_after_apply_when_config_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Minimal repo inventory so require_registered_repo passes.
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    _write(repo_root / ".pre-commit-config.yaml", "# test\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.apply as repo_apply_logic
    import main

    # Avoid owner resolution complexity.
    monkeypatch.setattr(repo_apply_logic, "resolved_repo_owner_ids", lambda **_kw: [])

    # Don't mutate repo attachment in this test.
    monkeypatch.setattr(repo_apply_logic, "attach_repo", lambda **_kw: None)

    # Force uv present and capture ordering.
    monkeypatch.setattr(repo_apply_logic, "_uv_exists", lambda: True)

    events: list[str] = []

    from cfg.repo.plan import RepoApplyPlan

    plan = RepoApplyPlan(cfg_root=cfg_root, repo_root=repo_root, operations=())
    monkeypatch.setattr(repo_apply_logic, "build_repo_apply_plan", lambda **_kw: plan)

    def fake_apply_repo_plan(_plan: RepoApplyPlan) -> int:
        events.append("apply")
        return 0

    def fake_run_cmd(argv: list[str], *, cwd: Any = None, check: bool = True, strip: bool = True) -> str:
        _ = cwd
        if argv[0:3] == ["git", "status", "--porcelain"]:
            return ""
        assert argv[0:3] == ["uvx", "pre-commit", "install"]
        events.append("install")
        return ""

    monkeypatch.setattr(repo_apply_logic, "apply_repo_plan", fake_apply_repo_plan)
    monkeypatch.setattr(repo_apply_logic, "run_cmd", fake_run_cmd)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "apply"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert events == ["apply", "install"]


def test_repo_apply_skips_precommit_install_in_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    _write(repo_root / ".pre-commit-config.yaml", "# test\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.apply as repo_apply_logic
    import main

    monkeypatch.setattr(repo_apply_logic, "resolved_repo_owner_ids", lambda **_kw: [])
    monkeypatch.setattr(repo_apply_logic, "attach_repo", lambda **_kw: None)
    monkeypatch.setattr(repo_apply_logic, "_uv_exists", lambda: True)

    from cfg.repo.plan import RepoApplyPlan

    plan = RepoApplyPlan(cfg_root=cfg_root, repo_root=repo_root, operations=())
    monkeypatch.setattr(repo_apply_logic, "build_repo_apply_plan", lambda **_kw: plan)
    monkeypatch.setattr(
        repo_apply_logic,
        "apply_repo_plan",
        lambda _plan: (_ for _ in ()).throw(RuntimeError("apply_repo_plan called")),
    )

    called = {"install": 0}

    def fake_run_cmd(*_a: Any, **_kw: Any) -> str:
        called["install"] += 1
        return ""

    monkeypatch.setattr(repo_apply_logic, "run_cmd", fake_run_cmd)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "apply", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert called["install"] == 0
