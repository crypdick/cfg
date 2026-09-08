from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

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


def _setup_cfg_root(tmp_path: Path, *, host_hint: str | None = None) -> Path:
    cfg_root = tmp_path / "cfg-root"
    _write(cfg_root / ".cfg-root", "")

    xdg = tmp_path / "xdg"
    _write(xdg / "cfg" / "root", str(cfg_root) + "\n")
    if host_hint is not None:
        _write(xdg / "cfg" / "host", host_hint + "\n")

    # Minimal feature manifests required for host init/apply logic in tests.
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/desktop")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/server")
    return cfg_root


def test_host_current_unset_and_host_init_sets_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint=None)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import main

    runner = CliRunner()

    res = runner.invoke(main.app, ["host", "current"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "(unset)" in res.output

    res2 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res2.exit_code == 0, (res2.output, res2.exception)
    assert "wrote:" in res2.output  # host hint file

    res3 = runner.invoke(main.app, ["host", "current"])
    assert res3.exit_code == 0
    assert "h1" in res3.output


def test_host_init_and_features_list_add_remove(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import main

    runner = CliRunner()
    # init (no owners needed for these tests)
    res = runner.invoke(main.app, ["host", "init", "h1", "--feature", "desktop"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "created:" in res.output or "updated:" in res.output

    # list
    res2 = runner.invoke(main.app, ["host", "feature", "list", "h1"])
    assert res2.exit_code == 0
    assert "features:" in res2.output
    assert "- desktop" in res2.output

    # add/remove
    res3 = runner.invoke(main.app, ["host", "feature", "add", "server", "h1"])
    assert res3.exit_code == 0
    res4 = runner.invoke(main.app, ["host", "feature", "remove", "desktop", "h1"])
    assert res4.exit_code == 0

    res5 = runner.invoke(main.app, ["host", "feature", "list", "h1"])
    assert res5.exit_code == 0
    assert "- server" in res5.output
    assert "- desktop" not in res5.output


def test_host_features_add_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import main

    runner = CliRunner()
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res0.exit_code == 0, (res0.output, res0.exception)

    inv = cfg_root / "hosts" / "h1" / "cfg.toml"
    before = inv.read_text(encoding="utf-8")

    res = runner.invoke(main.app, ["host", "feature", "add", "server", "h1", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "would update:" in res.output

    after = inv.read_text(encoding="utf-8")
    assert after == before


def test_host_features_list_not_registered_prints_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "feature", "list", "missing-host"])
    assert res.exit_code == 0
    assert "(host not registered)" in res.output
    assert "hint: run `cfg host init missing-host`" in res.output


def test_host_add_and_remove_manage_home_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Fake HOME so we can create a deterministic source file.
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / "a.txt", "hello\n")

    import main

    runner = CliRunner()
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res0.exit_code == 0

    # mirror (real write)
    res = runner.invoke(main.app, ["host", "mirror", "a.txt", "--host", "h1"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "added:" in res.output

    dest = cfg_root / "hosts" / "h1" / "overlay" / "a.txt"
    assert dest.is_file()

    # unmirror dry-run (would remove)
    res2 = runner.invoke(main.app, ["host", "unmirror", "a.txt", "--host", "h1", "--dry-run"])
    assert res2.exit_code == 0
    assert "would remove:" in res2.output
    assert dest.is_file()

    # unmirror (real)  # noqa: ERA001 -- section comment, not commented-out code
    res3 = runner.invoke(main.app, ["host", "unmirror", "a.txt", "--host", "h1"])
    assert res3.exit_code == 0
    assert "removed:" in res3.output
    assert not dest.exists()


def test_host_debug_inventory_print_generated_no_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.pyinfra.runtime_inventory as ri
    import main

    def fake_write_runtime_inventory(**_kw: Any) -> tuple[Path, Path]:
        inv_path = tmp_path / "inv.py"
        inv_path.write_text("# generated\n", encoding="utf-8")
        return inv_path, tmp_path / "tmpdir"

    cleaned: list[Path] = []

    monkeypatch.setattr(ri, "write_runtime_inventory", fake_write_runtime_inventory)
    monkeypatch.setattr(ri, "cleanup_runtime_inventory", cleaned.append)

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "debug-inventory", "--print", "--no-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "# generated" in res.output
    assert cleaned, "expected cleanup_runtime_inventory call"


def test_host_sync_repos_aggregates_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Minimal host inventory with two repos.
    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        """
name = "h1"
features = []


[repos]
"a/b" = "/tmp/a"
"c/d" = "/tmp/c"
""".lstrip(),
    )

    import cfg.host.logic.sync_repos as host_sync_logic
    import main

    class _Res:
        def __init__(self, repo_id: str, path: Path, fetched: bool, updated: bool, message: str):
            self.repo_id = repo_id
            self.path = path
            self.fetched = fetched
            self.updated = updated
            self.message = message

    def fake_sync_repo(*, repo_id: str, path: Path, **_kw: Any) -> _Res:
        if repo_id == "a/b":
            raise RuntimeError("boom")
        return _Res(repo_id, path, fetched=True, updated=False, message="fetched")

    monkeypatch.setattr(host_sync_logic, "sync_repo", fake_sync_repo)

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "sync-repos", "h1", "--fetch-only"])
    assert res.exit_code != 0
    assert res.exception is not None
    assert "Some repos failed to sync" in str(res.exception)


def test_host_run_dry_run_threads_to_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.workflows as host_workflows_logic
    import main

    # Avoid touching real inventory/workflow resolution.
    monkeypatch.setattr(host_workflows_logic, "resolve_targets", lambda *_a, **_k: ["@local"])
    monkeypatch.setattr(host_workflows_logic, "resolve_workflow_path", lambda *_a, **_k: Path("deploy.py"))
    monkeypatch.setattr(host_workflows_logic, "find_cfg_host", lambda *_a, **_k: "h1")

    called: dict[str, Any] = {}

    def fake_run_pyinfra(*, dry_run: bool, **kw: Any) -> None:
        called.update({"dry_run": dry_run, **kw})

    monkeypatch.setattr(host_workflows_logic, "run_pyinfra", fake_run_pyinfra)

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "run", "some-workflow", "--hosts", "@local", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert called["dry_run"] is True


def test_host_settings_not_registered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "settings", "missing-host"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "(host not registered)" in res.output


def test_host_settings_registered_prints_owner_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.settings as host_settings_logic
    import main

    monkeypatch.setattr(
        host_settings_logic,
        "resolve_host_owner_ids_for_host",
        lambda **_kw: ["host/feature/base", "host/feature/uv"],
    )

    runner = CliRunner()
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res0.exit_code == 0, (res0.output, res0.exception)

    res = runner.invoke(main.app, ["host", "settings", "h1"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "owners_resolved:" in res.output
    assert "host/feature/base" in res.output


def test_host_managed_empty_prints_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.managed as host_managed_logic
    import main

    monkeypatch.setattr(host_managed_logic, "resolve_host_owner_ids_for_host", lambda **_kw: [])

    runner = CliRunner()
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res0.exit_code == 0, (res0.output, res0.exception)

    res = runner.invoke(main.app, ["host", "managed", "h1"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "linked:" in res.output
    assert "mirrored:" in res.output
    assert "generated:" not in res.output


def test_host_add_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Fake HOME so we can create a deterministic source file.
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / "a.txt", "hello\n")

    import main

    runner = CliRunner()
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res0.exit_code == 0, (res0.output, res0.exception)

    res = runner.invoke(main.app, ["host", "mirror", "a.txt", "--host", "h1", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "would mirror:" in res.output

    dest = cfg_root / "hosts" / "h1" / "overlay" / "a.txt"
    assert not dest.exists()


def test_host_init_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "init", "h1", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "would create:" in res.output or "would update:" in res.output

    host_path = cfg_root / "hosts" / "h1" / "cfg.toml"
    assert not host_path.exists()


def test_host_init_uses_implicit_owner_without_derived_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint=None)
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import main

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "init", "h1"])
    assert res.exit_code == 0, (res.output, res.exception)

    host_settings_path = cfg_root / "hosts" / "h1" / "cfg.toml"
    assert host_settings_path.is_file()

    host_owner_manifest_path = cfg_root / "hosts" / "h1" / "host-manifest.toml"
    assert not host_owner_manifest_path.exists()

    from cfg.core.owners import load_owner_manifest_index

    assert "host/h1" in load_owner_manifest_index(cfg_root)


def test_host_apply_monkeypatches_pyinfra_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.apply as host_apply_logic
    import main

    called: dict[str, Any] = {}

    def fake_run_pyinfra(**kw: Any) -> None:
        called.update(kw)

    monkeypatch.setattr(host_apply_logic, "run_pyinfra", fake_run_pyinfra)

    runner = CliRunner()
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res0.exit_code == 0, (res0.output, res0.exception)

    res = runner.invoke(main.app, ["host", "apply", "h1"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert "home applied." in res.output
    assert called.get("current_host_for_local") == "h1"
    assert called.get("dry_run") is False


def test_host_apply_dry_run_passes_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.apply as host_apply_logic
    import main

    called: dict[str, Any] = {}

    def fake_run_pyinfra(**kw: Any) -> None:
        called.update(kw)

    monkeypatch.setattr(host_apply_logic, "run_pyinfra", fake_run_pyinfra)

    runner = CliRunner()
    res0 = runner.invoke(main.app, ["host", "init", "h1"])
    assert res0.exit_code == 0, (res0.output, res0.exception)

    res = runner.invoke(main.app, ["host", "apply", "h1", "--dry-run"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert called.get("dry_run") is True


def test_host_apply_yes_skips_pyinfra_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.apply as host_apply_logic
    import main

    called: dict[str, Any] = {}
    monkeypatch.setattr(host_apply_logic, "run_pyinfra", lambda **kw: called.update(kw))

    runner = CliRunner()
    assert runner.invoke(main.app, ["host", "init", "h1"]).exit_code == 0
    result = runner.invoke(main.app, ["host", "apply", "h1", "-y"])

    assert result.exit_code == 0, (result.output, result.exception)
    assert called["auto_approve"] is True


def test_host_upgrade_runs_separate_package_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.upgrade as host_upgrade_logic
    import main
    from cfg.host.cli_common import builtin_workflow_path

    called: dict[str, Any] = {}
    monkeypatch.setattr(host_upgrade_logic, "run_pyinfra", lambda **kw: called.update(kw))

    runner = CliRunner()
    init_result = runner.invoke(main.app, ["host", "init", "h1"])
    assert init_result.exit_code == 0, (init_result.output, init_result.exception)

    result = runner.invoke(main.app, ["host", "upgrade", "h1", "--dry-run"])
    assert result.exit_code == 0, (result.output, result.exception)
    assert "packages planned." in result.output
    assert called["deploy_file"] == builtin_workflow_path("upgrade_packages")
    assert called["current_host_for_local"] == "h1"
    assert called["dry_run"] is True


def test_host_run_workflow_uses_named_workflow_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = _setup_cfg_root(tmp_path, host_hint="h1")
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    import cfg.host.logic.workflows as host_workflows_logic
    import main
    from cfg.host.cli_common import builtin_workflow_path

    monkeypatch.setattr(host_workflows_logic, "resolve_targets", lambda *_a, **_kw: ["@local"])

    called: dict[str, Any] = {}

    def fake_run_pyinfra(**kw: Any) -> None:
        called.update(kw)

    monkeypatch.setattr(host_workflows_logic, "run_pyinfra", fake_run_pyinfra)

    runner = CliRunner()
    res = runner.invoke(main.app, ["host", "run", "apply_home", "--hosts", "@local"])
    assert res.exit_code == 0, (res.output, res.exception)
    assert str(builtin_workflow_path("apply_home")) == str(called.get("deploy_file"))
