from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.subprocess import run_cmd


def repo_root(cwd: Path | None = None) -> Path:
    root = run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(root).resolve()


def git_config_get(repo: Path, key: str) -> str | None:
    out = run_cmd(["git", "config", "--local", "--get", key], cwd=repo, check=False)
    return out or None


def origin_url(repo: Path) -> str | None:
    return git_config_get(repo, "remote.origin.url")


def git_dir(repo: Path) -> Path:
    """
    Resolve the actual git dir for a repo.

    Works for normal repos (.git is a dir) and worktrees/submodules where .git is a file
    containing `gitdir: ...`.
    """
    dotgit = repo / ".git"
    if dotgit.is_dir():
        return dotgit

    if dotgit.is_file():
        raw = dotgit.read_text(encoding="utf-8").strip()
        prefix = "gitdir:"
        if raw.startswith(prefix):
            rel = raw[len(prefix) :].strip()
            return (repo / rel).resolve()

    # Ask git directly when .git does not resolve the directory.
    gd = run_cmd(["git", "rev-parse", "--git-dir"], cwd=repo)
    p = Path(gd)
    return (repo / p).resolve() if not p.is_absolute() else p.resolve()


def staged_paths(repo: Path) -> list[str]:
    out = run_cmd(["git", "diff", "--cached", "--name-only"], cwd=repo, check=False)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def staged_file_content(repo: Path, relpath: str) -> str | None:
    try:
        return run_cmd(["git", "show", f":{relpath}"], cwd=repo, strip=False)
    except CfgError:
        return None
