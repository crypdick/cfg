from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from typer.testing import CliRunner

if TYPE_CHECKING:
    import pytest


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_feature_manifest(*, cfg_root: Path, owner_id: str) -> None:
    parts = owner_id.split("/")
    assert len(parts) >= 3, owner_id
    assert parts[1] == "feature", owner_id
    scope = parts[0]
    rel = Path(*parts[2:])
    path = cfg_root / "features" / scope / rel / "feature.toml"
    _write(
        path,
        ("schema_version = 1\nrequires = []\nconflicts = []\ngenerated = []\n"),
    )


def _init_git_repo(repo_root: Path, *, repo_id: str | None = "owner/repo") -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True)
    if repo_id:
        subprocess.run(
            ["git", "remote", "add", "origin", f"git@github.com:{repo_id}.git"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )


def _setup_cfg_root(tmp_path: Path, *, host_hint: str = "h1") -> Path:
    cfg_root = tmp_path / "cfg-root"
    _write(cfg_root / ".cfg-root", "")

    monkey_xdg = tmp_path / "xdg"
    _write(monkey_xdg / "cfg" / "root", str(cfg_root) + "\n")
    _write(monkey_xdg / "cfg" / "host", host_hint + "\n")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/uv")
    return cfg_root


def test_repo_check_returns_early_without_repo_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, repo_id=None)
    monkeypatch.chdir(repo_root)

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "check"])
    assert res.exit_code == 0


def test_repo_settings_unregistered_repo_prints_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.settings as repo_settings_logic
    import main

    # Avoid depending on real git dir internals.
    monkeypatch.setattr(repo_settings_logic, "git_dir", lambda _rr: repo_root / ".git")
    monkeypatch.setattr(repo_settings_logic, "git_config_get", lambda *_a, **_k: None)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "settings"])
    assert res.exit_code == 0
    assert "inventory: (not registered)" in res.output
    assert "hint: run `cfg repo init`" in res.output


def test_repo_settings_registered_prints_origin_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Register repo in inventory with origin_url so settings prints it.
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
origin_url = "git@github.com:owner/repo.git"
features = ["uv"]
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.settings as repo_settings_logic
    import main

    # Avoid depending on real git dir internals.
    monkeypatch.setattr(repo_settings_logic, "git_dir", lambda _rr: repo_root / ".git")
    monkeypatch.setattr(repo_settings_logic, "git_config_get", lambda *_a, **_k: None)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "settings"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "# Contents of" in res.output
    assert "origin_url" in res.output
    assert "git@github.com:owner/repo.git" in res.output


def test_repo_settings_returns_early_without_repo_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root, repo_id=None)
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.settings as repo_settings_logic
    import main

    # Avoid depending on real git dir internals.
    monkeypatch.setattr(repo_settings_logic, "git_dir", lambda _rr: repo_root / ".git")
    monkeypatch.setattr(repo_settings_logic, "git_config_get", lambda *_a, **_k: None)

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "settings"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "inventory: (no repo id; cannot look up repo cfg.toml)" in res.output


def test_repo_settings_includes_inventory_contents_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    inv = cfg_root / "repos" / "owner" / "repo" / "cfg.toml"
    _write(inv, 'id = "owner/repo"\nfeatures = []\n')

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "settings"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert f"# Contents of {inv.resolve()}" in res.output
    assert 'id = "owner/repo"' in res.output
    assert "---" in res.output
    assert "# Detailed list of specific files being managed" in res.output


def test_repo_features_list_not_registered_prints_message(
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
    res = runner.invoke(main.app, ["repo", "feature", "list"])
    assert res.exit_code == 0
    assert "(repo not registered)" in res.output


def test_repo_features_add_updates_origin_url_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Repo is registered but missing origin_url.
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

    import cfg.repo.logic.features as repo_features_logic
    import main

    monkeypatch.setattr(
        repo_features_logic, "origin_url", lambda *_a, **_k: "https://github.com/owner/repo.git"
    )

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "feature", "add", "uv"])
    assert res.exit_code == 0, (res.output, res.exception)

    data = tomllib.loads((cfg_root / "repos" / "owner" / "repo" / "cfg.toml").read_text(encoding="utf-8"))
    assert data["origin_url"] == "https://github.com/owner/repo.git"
    assert "uv" in data["features"]


def test_repo_features_remove_updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = ["uv"]
""".lstrip(),
    )

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    _write(repo_root / ".cfg" / "repo_id", "owner/repo\n")
    monkeypatch.chdir(repo_root)

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "feature", "remove", "uv"])
    assert res.exit_code == 0, (res.output, res.exception)

    data = tomllib.loads((cfg_root / "repos" / "owner" / "repo" / "cfg.toml").read_text(encoding="utf-8"))
    assert data["features"] == []


def test_repo_link_delegates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.linking as repo_linking_logic
    import main

    monkeypatch.setattr(repo_linking_logic, "link_repo_file", lambda **_kw: Path("/tmp/linked"))

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "link", "a.txt", "--feature", "python"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "linked to:" in res.output


def test_repo_settings_nonempty_prints_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    class _TF:
        def __init__(self, owner: str, src: str):
            self.owner = owner
            self.src = src

    class _Plan:
        desired: ClassVar[dict[Path, _TF]] = {Path("a.txt"): _TF(owner="repo/x", src="/tmp/a")}

    monkeypatch.setattr(
        repo_settings_logic, "resolve_owner_files", lambda **_kw: type("_R", (), {"desired": _Plan.desired})()
    )

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "settings"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "linked:" in res.output
    assert "mirrored:" in res.output
    assert "generated:" in res.output
    assert "a.txt" in res.output


def test_repo_remove_not_managed_prints_no_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "unmirror", "missing.txt"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "no change (not managed)." in res.output


def test_repo_check_calls_drift_checker_when_registered(
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
    monkeypatch.chdir(repo_root)

    import cfg.repo.logic.check as repo_check_logic
    import main

    monkeypatch.setattr(repo_check_logic, "resolved_repo_owner_ids", lambda **_kw: ["repo/feature/a"])

    called: dict[str, Any] = {}
    monkeypatch.setattr(repo_check_logic, "check_repo_precommit_drift", lambda **kw: called.update(kw))

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "check", "--staged"])
    assert res.exit_code == 0
    assert called.get("staged") is True


def test_repo_check_rejects_cursor_rules_under_repo_feature_when_not_nested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("GIT_INDEX_FILE", raising=False)
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)

    # Simulate committing inside the personalization repository itself.
    _init_git_repo(cfg_root, repo_id=None)
    monkeypatch.chdir(cfg_root)

    bad = cfg_root / "features" / "repo" / "my-feature" / "overlay" / ".cursor" / "rules" / "not-nested.mdc"
    _write(bad, "rule: nope\n")
    subprocess.run(["git", "add", bad.as_posix()], cwd=str(cfg_root), check=True, capture_output=True)

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "check", "--staged"])
    assert res.exit_code == 1
    # Typer prints CfgError messages to stderr, but Click/Typer versions differ in how
    # (or whether) stderr is exposed on the Result. The most robust assertion is against
    # the exception string itself.
    msg = str(res.exception or "")
    assert "Invalid Cursor config layout under repo/feature payload(s)." in msg
    assert "features/repo" in msg
    assert "not-nested.mdc" in msg


def test_repo_check_allows_cursor_rules_under_repo_feature_when_nested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("GIT_INDEX_FILE", raising=False)
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)

    _init_git_repo(cfg_root, repo_id=None)
    monkeypatch.chdir(cfg_root)

    good = (
        cfg_root
        / "features"
        / "repo"
        / "my-feature"
        / "overlay"
        / ".cursor"
        / "rules"
        / "my-feature"
        / "ok.mdc"
    )
    _write(good, "rule: ok\n")
    subprocess.run(["git", "add", good.as_posix()], cwd=str(cfg_root), check=True, capture_output=True)

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "check", "--staged"])
    assert res.exit_code == 0, (res.output, res.exception)


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
    monkeypatch.setattr(repo_apply_logic, "resolve_host_owner_ids_implied_by_repo", lambda **_kw: [])

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
    monkeypatch.setattr(repo_apply_logic, "resolve_host_owner_ids_implied_by_repo", lambda **_kw: [])

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
    monkeypatch.setattr(repo_apply_logic, "resolve_host_owner_ids_implied_by_repo", lambda **_kw: [])

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
    monkeypatch.setattr(repo_apply_logic, "resolve_host_owner_ids_implied_by_repo", lambda **_kw: [])

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
    monkeypatch.setattr(repo_apply_logic, "resolve_host_owner_ids_implied_by_repo", lambda **_kw: [])
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
