from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.subprocess import run_cmd
from cfg.repo.attach import attach_repo, validate_repo_attachment
from cfg.repo.cli_common import repo_ctx, require_registered_repo, resolved_repo_owner_ids
from cfg.repo.git import git_dir
from cfg.repo.plan import apply_repo_plan, build_repo_apply_plan, format_repo_plan

PRECOMMIT_PATH = Path(".pre-commit-config.yaml")


def _uv_exists() -> bool:
    try:
        out = run_cmd(["uv", "--version"], check=False)
    except CfgError:
        return False
    return bool(str(out or "").strip())


def _ensure_precommit_installed(*, repo_root: Path, cfg_root: Path) -> list[str]:
    """Install pre-commit hooks if the repo is configured for it.

    Runs after apply so `.pre-commit-config.yaml` is already up to date. Returns
    note lines to surface to the user; empty when the hook was installed cleanly
    (or there is nothing to do).
    """
    precommit_cfg = repo_root / PRECOMMIT_PATH
    if not precommit_cfg.is_file():
        return []
    if not _uv_exists():
        return ["note: uv is not installed; skipping `uvx pre-commit install`."]

    hook_path = git_dir(repo_root) / "hooks" / "pre-commit"
    hook_text = hook_path.read_text(encoding="utf-8") if hook_path.is_file() else ""
    cfg_hook = str((cfg_root / "hooks" / "pre-commit").resolve())
    is_cfg_hook = cfg_hook in hook_text
    is_precommit_hook = "pre_commit" in hook_text or "pre-commit" in hook_text

    # If a user has a custom hook, don't clobber it.
    if hook_path.exists() and not (is_cfg_hook or is_precommit_hook):
        return [
            "note: repo has a custom .git/hooks/pre-commit; skipping `uvx pre-commit install` (run `uvx pre-commit install --overwrite` manually if desired)."
        ]

    run_cmd(["uvx", "pre-commit", "install", "--install-hooks", "--overwrite"], cwd=repo_root, check=True)
    return []


def apply(*, allow_dirty: bool, dry_run: bool) -> list[str]:
    """Business logic for `cfg repo apply` (returns lines to print)."""
    ctx, rr, rid = repo_ctx()
    cfg = require_registered_repo(ctx, rid, include_hint=True)

    lines: list[str] = []
    snapshot = ctx.snapshot
    repo_owner_ids = resolved_repo_owner_ids(
        cfg_root=ctx.root,
        cfg=cfg,
        manifest_index=snapshot.manifest_index,
    )

    # Refuse before planning or performing any mutation.
    if not allow_dirty and not dry_run:
        dirty = run_cmd(["git", "status", "--porcelain"], cwd=rr, check=False, strip=False).strip()
        if dirty:
            raise CfgError(
                "Repo is dirty; refusing to apply managed files.\n\n"
                "Hint: re-run with --allow-dirty if this is intentional.\n\n"
                f"git status --porcelain:\n{dirty}"
            )

    previous_state = validate_repo_attachment(repo_root=rr)

    # Resolve and validate every repo destination before host, cfg-root, or repo mutation.
    plan = build_repo_apply_plan(
        cfg_root=ctx.root,
        repo_root=rr,
        repo_id=rid,
        enabled_owner_ids=repo_owner_ids,
        manifest_index=snapshot.manifest_index,
        previous_state=previous_state,
        path_provider_overrides=cfg.path_provider_overrides,
    )

    if dry_run:
        lines.append("note: --dry-run set; skipping repo attachment step.")
        lines.append("would apply:")
        lines.extend(format_repo_plan(plan) or ["- no managed file changes"])
    else:
        # Ensure local integration only after the complete managed-file plan has
        # passed validation.
        attach_repo(repo_root=rr, cfg_root=ctx.root)
        changed = apply_repo_plan(plan)
        lines.append(f"changed: {changed} managed repo path(s)")

    # Ensure pre-commit is installed if the repo is configured for it.
    # This intentionally happens after apply so `.pre-commit-config.yaml` is up to date.
    if not dry_run:
        lines.extend(_ensure_precommit_installed(repo_root=rr, cfg_root=ctx.root))
    lines.append("planned." if dry_run else "applied.")
    return lines
