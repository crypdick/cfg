from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cfg.core.errors import CfgError
from cfg.core.inventory import load_inventory


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


def test_load_inventory_toml_only_happy_path(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    _write(
        cfg_root / "hosts" / "h1" / "cfg.toml",
        """
name = "h1"
features = ["desktop"]

[repos]
"owner/repo" = "/tmp/repo"
""".lstrip(),
    )
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = ["uv"]
""".lstrip(),
    )

    inv = load_inventory(cfg_root)

    assert set(inv.hosts.keys()) == {"h1"}
    assert set(inv.repos.keys()) == {"owner/repo"}

    assert inv.hosts["h1"].settings.features == ["desktop"]
    assert inv.hosts["h1"].settings.repos["owner/repo"] == Path("/tmp/repo")

    repo = inv.repos["owner/repo"].settings
    assert repo.features == ["uv"]


def test_load_inventory_does_not_load_settings_py(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    _write(
        cfg_root / "hosts" / "h2" / "settings.py",
        """
from cfg.core.models import HostSettings
SETTINGS = HostSettings(name="h2", features=["desktop"])
""".lstrip(),
    )

    inv = load_inventory(cfg_root)
    assert "h2" not in inv.hosts


def test_host_toml_name_must_match_filename(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    _write(
        cfg_root / "hosts" / "h3" / "cfg.toml",
        'name = "not-h3"\n',
    )

    with pytest.raises(CfgError, match="must match filename stem"):
        load_inventory(cfg_root)


def test_repo_toml_id_must_match_path(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        'id = "someoneelse/repo"\n',
    )

    with pytest.raises(CfgError, match="must match its location"):
        load_inventory(cfg_root)


def test_cfg_host_init_writes_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/base")
    _write_feature_manifest(cfg_root=cfg_root, owner_id="host/feature/desktop")
    monkeypatch.chdir(cfg_root)
    # Ensure the CLI uses this temp cfg root even if the outer environment has CFG_ROOT set.
    monkeypatch.setenv("CFG_ROOT", str(cfg_root))
    # Prevent leaking host hint writes into the real user config (~/.config/cfg/host).
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    # Import after chdir so require_cfg_root walks up to this temp root.
    import main

    runner = CliRunner()
    res = runner.invoke(
        main.app,
        [
            "host",
            "init",
            "my-host",
            "--feature",
            "desktop",
            "--repo",
            "owner/repo=/tmp/repo",
        ],
    )
    assert res.exit_code == 0, res.output

    host_settings = cfg_root / "hosts" / "my-host" / "cfg.toml"
    assert host_settings.is_file()
    inv = load_inventory(cfg_root)
    # macOS gotcha: /tmp is a symlink to /private/tmp, so paths get resolved.
    # Use .resolve() to normalize before comparison.
    assert inv.hosts["my-host"].settings.repos["owner/repo"] == Path("/tmp/repo").resolve()


def test_inventory_loads_host_and_repo_dirs(tmp_path: Path) -> None:
    """
    Legacy layout used to live under:
    - hosts/<host>/cfg.toml
    - repos/<owner>/<repo>/cfg.toml
    These should be loaded.
    """
    cfg_root = tmp_path
    _write(cfg_root / ".cfg-root", "")

    _write(cfg_root / "hosts" / "h1" / "cfg.toml", 'name="h1"\n')
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        'id="owner/repo"\nfeatures=["uv"]\n',
    )

    inv = load_inventory(cfg_root)
    assert "h2" not in inv.hosts
    assert "owner/repo" in inv.repos
