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
    _write_feature_manifest(cfg_root=cfg_root, owner_id="repo/feature/python")
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
    monkeypatch.setattr(repo_check_logic, "check_generated_files_drift", lambda **kw: called.update(kw))

    runner = CliRunner()
    res = runner.invoke(main.app, ["repo", "check", "--staged"])
    assert res.exit_code == 0
    assert called.get("staged") is True
