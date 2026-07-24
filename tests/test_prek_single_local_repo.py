from __future__ import annotations

import tomllib
from pathlib import Path


def test_prek_config_has_single_local_repo_section() -> None:
    """Keep project-local checks consolidated in one native local repository."""
    cfg = tomllib.loads(Path("prek.toml").read_text(encoding="utf-8"))
    assert isinstance(cfg, dict)

    repos = cfg.get("repos")
    assert isinstance(repos, list)

    local_repos = [repo for repo in repos if isinstance(repo, dict) and repo.get("repo") == "local"]
    assert len(local_repos) == 1, f"expected exactly one local repo, got {len(local_repos)}"

    hooks = local_repos[0]["hooks"]
    assert isinstance(hooks, list)
    hook_ids = {hook.get("id") for hook in hooks if isinstance(hook, dict)}

    expected = {"fix-future-annotations", "pytest", "cfg-repo-check"}
    assert expected.issubset(hook_ids), f"missing local hooks: {sorted(expected - hook_ids)}"
