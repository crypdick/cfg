from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from cfg.pyinfra.execute import PYINFRA_BOOTSTRAP


@pytest.mark.parametrize(
    ("same", "dry_run", "force"),
    [(True, False, False), (False, False, False), (True, True, False), (False, False, True)],
)
def test_home_apply_handles_existing_regular_file(
    tmp_path: Path, same: bool, dry_run: bool, force: bool
) -> None:
    root = tmp_path / "cfg"
    source = root / "features/host/example/overlay/.config/example.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"managed\x00bytes\n")
    (root / "features/host/example/feature.toml").write_text(
        "schema_version = 1\nrequires = []\nconflicts = []\ngenerated = []\n", encoding="utf-8"
    )
    home = tmp_path / "home"
    dest = home / ".config/example.json"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(source.read_bytes() if same else b"different\n")
    inventory = tmp_path / "inventory.py"
    inventory.write_text(
        f"all = [('@local', {{'_cfg_root': {str(root)!r}, '_cfg_host_name': 'h1', "
        "'_cfg_host_owner_ids': ['host/feature/example']})]\n",
        encoding="utf-8",
    )
    workflow = Path(__file__).resolve().parents[1] / "cfg/host/workflows/apply_home.py"
    env = {**os.environ, "HOME": str(home)}
    env.pop("CFG_FORCE_LINKS", None)
    if force:
        env["CFG_FORCE_LINKS"] = "1"
    command = [sys.executable, "-c", PYINFRA_BOOTSTRAP, str(inventory), str(workflow), "--yes"]
    if dry_run:
        command.append("--dry")
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if dry_run:
        assert result.returncode == 0, result.stdout + result.stderr
        assert not dest.is_symlink()
        assert dest.read_bytes() == source.read_bytes()
    elif same or force:
        assert result.returncode == 0, result.stdout + result.stderr
        assert dest.is_symlink()
        assert dest.resolve() == source
    else:
        assert result.returncode != 0
        assert not dest.is_symlink()
        assert dest.read_bytes() == b"different\n"
        assert str(dest) in result.stdout + result.stderr
        assert str(source) in result.stdout + result.stderr
        assert "compare" in (result.stdout + result.stderr).lower()
        assert "consolidate" in (result.stdout + result.stderr).lower()
