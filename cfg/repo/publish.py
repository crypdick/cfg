from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cfg.core.ids import OwnerId
from cfg.owners.fs import OwnerFile, owner_mirror_files, resolve_owner_files


@dataclass(frozen=True)
class PublishPlan:
    """
    Plan for copying publish payload files into a repo working tree.

    - desired maps repo-relative paths -> a single chosen provider file (OwnerFile).
    - all_known_rels is the set of all publish paths known to cfg (across all owners + repo-specific),
      used for future "prune stale" features.
    """

    desired: dict[Path, OwnerFile]
    all_known_rels: set[Path]


def _mirror_file_getter(cfg_root: Path, owner_id: OwnerId) -> list[OwnerFile]:
    return owner_mirror_files(cfg_root=cfg_root, owner_id=owner_id)


def resolve_repo_publish_files(
    *,
    cfg_root: Path,
    enabled_owner_ids: Sequence[OwnerId],
    path_provider_overrides: Mapping[str, str] | None = None,
) -> PublishPlan:
    """
    Resolve publish file providers for a repo.

    Conflicts:
    - If multiple enabled owners provide the same relative path, this is a hard
      error unless `path_provider_overrides` chooses a provider owner id for that path.
    """
    resolved = resolve_owner_files(
        cfg_root=cfg_root,
        enabled_owner_ids=enabled_owner_ids,
        file_getter=_mirror_file_getter,
        path_provider_overrides=path_provider_overrides,
        conflict_error_prefix="Publish file conflict",
    )
    return PublishPlan(desired=resolved.desired, all_known_rels=resolved.all_known_rels)
