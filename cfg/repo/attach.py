from __future__ import annotations

from pathlib import Path

from cfg.core.models import RepoStateManifest
from cfg.core.state import read_repo_state, write_repo_state
from cfg.core.subprocess import run_cmd
from cfg.repo.git import git_config_get, git_dir, origin_url
from cfg.repo.identity import normalize_repo_id

DEFAULT_LOCAL_IGNORES = [
    # Cursor local config/tooling
    "/.cursor/",
    # direnv
    "/.envrc",
    # cfg local state
    "/.cfg/",
]


def validate_repo_attachment(*, repo_root: Path) -> RepoStateManifest:
    """Validate attachment inputs and return the existing state without writing."""
    state = read_repo_state(repo_root)
    url = origin_url(repo_root)
    if url:
        normalize_repo_id(url)
    return state


def attach_repo(
    *,
    repo_root: Path,
    cfg_root: Path,
    ignores: list[str] | None = None,
) -> None:
    """
    Attach cfg to a git repo:
    - remove cfg's private-root pre-commit shim when present
    - add local ignore patterns to .git/info/exclude
    - record undo state in .cfg/state.json

    Note on hooks:
    - Hook installation is owned by standard pre-commit tooling after managed files
      have been applied.
    - We intentionally do NOT set `core.hooksPath` because it breaks `pre-commit install`.
    """
    state = validate_repo_attachment(repo_root=repo_root)

    cfg_hook = (cfg_root / "hooks" / "pre-commit").resolve()
    cfg_hooks_path = str((cfg_root / "hooks").resolve())
    cur_hooks = git_config_get(repo_root, "core.hooksPath")

    # If this repo was previously attached with hooksPath pointing at cfg, unset it so
    # standard tooling works again.
    if cur_hooks == cfg_hooks_path:
        if state.attach.prev_core_hooks_path is None:
            state.attach.prev_core_hooks_path = None
        run_cmd(
            ["git", "config", "--local", "--unset-all", "core.hooksPath"],
            cwd=repo_root,
            check=False,
        )

    hooks_dir = git_dir(repo_root) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"

    if hook_path.is_file():
        hook_text = hook_path.read_text(encoding="utf-8")
        legacy_exec = f'exec "{cfg_hook}"'
        if legacy_exec in hook_text:
            hook_path.unlink()

    exclude_file = git_dir(repo_root) / "info" / "exclude"
    exclude_file.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_file.read_text(encoding="utf-8") if exclude_file.is_file() else ""
    lines = [ln.rstrip("\n") for ln in existing.splitlines()]
    wanted = ignores or DEFAULT_LOCAL_IGNORES
    changed = False
    added: list[str] = []
    for pat in wanted:
        if pat not in lines:
            lines.append(pat)
            changed = True
            added.append(pat)

    if changed:
        exclude_file.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")

    if added:
        # Preserve history, avoid duplicates.
        prev = list(state.attach.exclude_patterns_added or [])
        for pat in added:
            if pat not in prev:
                prev.append(pat)
        state.attach.exclude_patterns_added = prev

    write_repo_state(repo_root, state)
