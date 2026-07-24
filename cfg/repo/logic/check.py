from __future__ import annotations

from cfg.core.context import CfgContext
from cfg.repo.cli_common import resolved_repo_owner_ids
from cfg.repo.generated_drift import check_repo_precommit_drift
from cfg.repo.git import repo_root


def check(*, staged: bool) -> None:
    """Business logic for `cfg repo check`."""
    ctx = CfgContext.load()
    rr = repo_root()

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
