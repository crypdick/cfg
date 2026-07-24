from __future__ import annotations

from pathlib import Path  # noqa: TC003 -- Pydantic needs Path at runtime for model field validation
from types import SimpleNamespace
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from cfg.core.inventory import Inventory, Loaded
from cfg.core.models import HostSettings, RepoSettings, SshSettings
from cfg.pyinfra import runtime_inventory as ri

if TYPE_CHECKING:
    import pytest


class _ModelWithPath(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path


def test_jsonish_converts_paths_and_models(tmp_path: Path) -> None:
    assert ri._jsonish(None) is None
    assert ri._jsonish(1) == 1
    assert ri._jsonish(tmp_path) == str(tmp_path)

    m = _ModelWithPath(path=tmp_path / "x")
    out = ri._jsonish(m)
    assert out == {"path": str(tmp_path / "x")}

    out2 = ri._jsonish({"a": tmp_path, "b": {1, 2}})
    assert out2["a"] == str(tmp_path)
    assert sorted(out2["b"]) == [1, 2]


def test_add_host_to_group_ignores_empty_and_underscore() -> None:
    groups: dict[str, list[str]] = {}
    ri._add_host_to_group(groups, "", "h1")
    ri._add_host_to_group(groups, "   ", "h1")
    ri._add_host_to_group(groups, "_hidden", "h1")
    assert groups == {}

    ri._add_host_to_group(groups, "desktop", "h1")
    assert groups == {"desktop": ["h1"]}


def test_host_data_flattens_vars_without_overwriting_reserved_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ri, "resolve_host_owner_ids_for_host", lambda **_kw: ["host/feature/base"])

    fake = SimpleNamespace(
        name="h1",
        features=[],
        repos={"owner/repo": tmp_path / "repo"},
        vars={"a": 1, "_cfg_host_name": "nope"},
        ssh=SshSettings(host="1.2.3.4", user="me", port=2222),
    )
    inv = Inventory(repos={}, hosts={})
    data = ri._host_data(settings=fake, cfg_root=tmp_path, cfg_inventory=inv)  # type: ignore[arg-type]  # duck-typed SimpleNamespace satisfies HostSettingsLike at runtime

    assert data["_cfg_host_name"] == "h1"
    assert data["_cfg_host_owner_ids"] == ["host/feature/base"]
    assert data["a"] == 1
    # Reserved key should not be overwritten by vars flattening.
    assert data["_cfg_host_name"] == "h1"
    assert data["ssh_hostname"] == "1.2.3.4"
    assert data["ssh_user"] == "me"
    assert data["ssh_port"] == 2222


def test_build_groups_includes_hosts_and_optional_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ri, "resolve_host_owner_ids_for_host", lambda **_kw: ["host/feature/base"])

    host1 = HostSettings(
        name="h1",
        features=["desktop", "desktop"],
        repos={"owner/repo": tmp_path / "repo"},
        vars={"x": "y"},
    )
    host2 = HostSettings(name="h2", features=["server"], vars={})

    repo = RepoSettings(id="owner/repo", features=["uv"])
    inv = Inventory(
        hosts={
            "h1": Loaded(settings=host1, source_path=tmp_path / "h1.toml"),
            "h2": Loaded(settings=host2, source_path=tmp_path / "h2.toml"),
        },
        repos={"owner/repo": Loaded(settings=repo, source_path=tmp_path / "r.toml")},
    )

    groups = ri.build_groups(
        cfg_inventory=inv,
        cfg_root=tmp_path,
        current_host_for_local="h1",
        include_local=True,
    )

    assert "all" in groups
    # all group contains tuples (name, data)
    all_names = [t[0] for t in groups["all"]]
    assert all_names == ["h1", "h2", "@local"]

    assert groups["desktop"] == ["h1", "@local"]
    assert groups["server"] == ["h2"]

    # Local host data includes cfg root and the configured owner ids.
    local = next(t for t in groups["all"] if t[0] == "@local")
    local_data = local[1]
    assert local_data["_cfg_root"] == str(tmp_path)
    assert local_data["_cfg_host_owner_ids"] == ["host/feature/base"]


def test_write_and_cleanup_inventory_file(tmp_path: Path) -> None:
    inv_path, tmpdir = ri.write_inventory_file(
        groups={"all": [("h1", {"a": 1})], "desktop": ["h1"]},
        header_lines=["# header", "# ruff: noqa"],
    )
    assert inv_path.is_file()
    content = inv_path.read_text(encoding="utf-8")
    assert "GROUPS =" in content
    assert "globals().update(GROUPS)" in content
    assert "subprocess._USE_VFORK = False" in content
    assert "_posixsubprocess" in content
    assert "subprocess._fork_exec" in content

    ri.cleanup_runtime_inventory(tmpdir)
    assert not tmpdir.exists()
