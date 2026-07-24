from __future__ import annotations

from pathlib import Path, PurePosixPath

from cfg.core.context import CfgContext
from cfg.core.errors import CfgError
from cfg.repo.cli_common import resolved_repo_owner_ids
from cfg.repo.generated_drift import check_repo_precommit_drift
from cfg.repo.git import repo_root, staged_paths


def _check_cursor_feature_paths_are_nested(*, cfg_root: Path, repo_root: Path, staged: bool) -> None:
    """
    Enforce repo/feature payload layout for Cursor config.

    Rule: any `.cursor/rules/*` or `.cursor/commands/*` files under
    `features/repo/**` must be nested under an additional directory:

    - `.cursor/rules/<group>/*.mdc`
    - `.cursor/commands/<group>/*`

    This is scoped to the personalization repository by requiring `repo_root == cfg_root`, so it
    cannot accidentally fire in attached repos.
    """
    # Only when checking staged content (git hooks).
    if not staged:
        return
    if repo_root.resolve() != cfg_root.resolve():
        return

    bad: list[str] = []
    for rel in staged_paths(repo_root):
        p = PurePosixPath(rel)
        parts = p.parts

        # Only enforce inside repo feature payloads.
        if len(parts) < 2 or parts[:2] != ("features", "repo"):
            continue

        # Look for `.cursor/{rules,commands,command}/...`
        for i, part in enumerate(parts):
            if part != ".cursor":
                continue
            if i + 1 >= len(parts):
                continue
            kind = parts[i + 1]
            if kind not in ("rules", "commands", "command"):
                continue

            rest = parts[i + 2 :]
            # `.cursor/rules/<file>` (no group dir) is forbidden.
            if len(rest) == 1:
                bad.append(rel)
            break

    if not bad:
        return

    bad_list = "\n".join(f"- {p}" for p in sorted(set(bad)))
    raise CfgError(
        "Invalid Cursor config layout under repo/feature payload(s).\n\n"
        "Rule: any `.cursor/rules` or `.cursor/commands` added under `features/repo/**` "
        "must be nested under a directory.\n\n"
        "Examples:\n"
        "- `.cursor/rules/<feature-name>/*.mdc`\n"
        "- `.cursor/commands/<feature-name>/*`\n\n"
        "Bad path(s):\n"
        f"{bad_list}\n"
    )


def check(*, staged: bool) -> None:
    """Business logic for `cfg repo check`."""
    ctx = CfgContext.load()
    rr = repo_root()

    # Personalization-repo-only checks should run even if the current repo is not registered.
    _check_cursor_feature_paths_are_nested(cfg_root=ctx.root, repo_root=rr, staged=staged)

    rid = ctx.repo_id
    if not rid:
        return

    cfg = ctx.store.get_repo(rid)
    if not cfg:
        return

    owner_ids = resolved_repo_owner_ids(cfg_root=ctx.root, cfg=cfg)
    check_repo_precommit_drift(
        cfg_root=ctx.root,
        repo_root=rr,
        repo_id=rid,
        repo_cfg=cfg,
        enabled_owner_ids=owner_ids,
        staged=staged,
    )
