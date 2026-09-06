from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.host.deploys import ensure
from cfg.pyinfra.execute import run_pyinfra_cli

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("contents", [None, "modified", "expected"])
def test_remove_apt_repo_requires_exact_contents(
    monkeypatch: pytest.MonkeyPatch, contents: str | None
) -> None:
    import hashlib

    operations = []
    digest = hashlib.sha256(contents.encode()).hexdigest() if contents is not None else None
    monkeypatch.setattr(ensure, "is_linux", lambda: True)
    monkeypatch.setattr(
        ensure,
        "host",
        SimpleNamespace(
            get_fact=lambda fact, **_kwargs: (
                (None if contents is None else {}) if fact is ensure.File else digest
            )
        ),
    )
    monkeypatch.setattr(ensure.files, "file", lambda **kwargs: operations.append(kwargs))
    if contents == "modified":
        with pytest.raises(CfgError, match="modified"):
            ensure.remove_apt_repo(repo_filename="retired", expected_content="expected")
    else:
        ensure.remove_apt_repo(repo_filename="retired", expected_content="expected")
    assert [operation["path"] for operation in operations] == (
        ["/etc/apt/sources.list.d/retired.list"] if contents == "expected" else []
    )


@pytest.mark.parametrize("dry_run", [False, True])
def test_all_sources_prepare_before_any_feature_deploy(tmp_path: Path, dry_run: bool) -> None:
    cfg_root = tmp_path / "cfg"
    prepared = tmp_path / "prepared"
    deployed = tmp_path / "deployed"
    first = cfg_root / "features/host/first"
    last = cfg_root / "features/host/last"
    first.mkdir(parents=True)
    last.mkdir(parents=True)
    (last / "prepare.py").write_text(
        "from pyinfra.operations import files\n"
        f"def main():\n    files.file(path={str(prepared)!r}, present=True)\n"
    )
    (first / "deploy.py").write_text(
        "from pyinfra.operations import server\n"
        f"def main():\n    server.shell(commands=['test -f {prepared} && touch {deployed}'])\n"
    )
    inventory = tmp_path / "inventory.py"
    inventory.write_text(
        f"all = [('@local', {{'_cfg_root': {str(cfg_root)!r}, '_cfg_host_owner_ids': ['host/feature/first', 'host/feature/last']}})]\n"
    )
    workflow = tmp_path / "workflow.py"
    workflow.write_text("from cfg.host.deploys.feature_deploys import deploy_features\ndeploy_features()\n")
    run_pyinfra_cli(
        cwd=tmp_path, inventory_path=inventory, operations=[str(workflow)], dry_run=dry_run, quiet=True
    )
    assert deployed.exists() is not dry_run
    assert prepared.exists() is not dry_run


@pytest.mark.parametrize("filename", ["../foreign", "/etc/apt/sources.list", "", "x;rm"])
def test_source_retirement_rejects_invalid_filenames(filename: str) -> None:
    with pytest.raises(CfgError, match="Invalid APT source filename"):
        ensure.remove_apt_repo(repo_filename=filename, expected_content="expected")


def test_upgrade_prepares_before_package_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    from cfg.host.cli_common import builtin_workflow_path
    from cfg.host.deploys import feature_deploys, pkg

    calls = []
    monkeypatch.setattr(feature_deploys, "prepare_features", lambda: calls.append("prepare"))
    monkeypatch.setattr(pkg, "pkg_update", lambda: calls.append("update"))
    monkeypatch.setattr(pkg, "pkg_upgrade", lambda: calls.append("upgrade"))
    runpy.run_path(str(builtin_workflow_path("upgrade_packages")))
    assert calls == ["prepare", "update", "upgrade"]
