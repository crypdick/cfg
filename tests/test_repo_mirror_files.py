from __future__ import annotations

from pathlib import Path

import pytest

from cfg.core.errors import CfgError
from cfg.repo.plan import resolve_repo_outputs


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_resolve_repo_outputs_detects_mirror_conflicts(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / "features" / "repo" / "a" / "mirror" / "x.txt", "a\n")
    _write(cfg_root / "features" / "repo" / "b" / "mirror" / "x.txt", "b\n")
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "repo" / "b" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )

    with pytest.raises(CfgError, match="Mirror conflict"):
        resolve_repo_outputs(
            cfg_root=cfg_root,
            repo_id="owner/repo",
            enabled_owner_ids=["repo/feature/a", "repo/feature/b"],
        )


def test_resolve_repo_outputs_mirror_override_picks_provider(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / "features" / "repo" / "a" / "mirror" / "x.txt", "a\n")
    _write(cfg_root / "features" / "repo" / "b" / "mirror" / "x.txt", "b\n")
    _write(
        cfg_root / "features" / "repo" / "a" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )
    _write(
        cfg_root / "features" / "repo" / "b" / "feature.toml",
        """
schema_version = 1
requires = []
conflicts = []
generated = []
""".lstrip(),
    )

    outputs = resolve_repo_outputs(
        cfg_root=cfg_root,
        repo_id="owner/repo",
        enabled_owner_ids=["repo/feature/a", "repo/feature/b"],
        path_provider_overrides={"x.txt": "repo/feature/b"},
    )
    assert outputs.mirrors.desired[Path("x.txt")].owner == "repo/feature/b"


def test_resolve_repo_outputs_selects_single_mirror_provider(tmp_path: Path) -> None:
    cfg_root = tmp_path
    _write(cfg_root / "repos" / "owner" / "repo" / "mirror" / "x.txt", "repo\n")
    _write(
        cfg_root / "repos" / "owner" / "repo" / "cfg.toml",
        """
id = "owner/repo"
features = []
""".lstrip(),
    )
    outputs = resolve_repo_outputs(
        cfg_root=cfg_root,
        repo_id="owner/repo",
        enabled_owner_ids=["repo/owner/repo"],
    )
    assert outputs.mirrors.desired[Path("x.txt")].owner == "repo/owner/repo"
