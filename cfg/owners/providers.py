"""Select one provider per output path for payloads and generated files."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from cfg.core.errors import CfgError


class PathProvider(Protocol):
    @property
    def owner(self) -> str: ...


def select_path_providers[Provider: PathProvider](
    providers: Mapping[Path, Sequence[Provider]],
    *,
    path_provider_overrides: Mapping[str, str],
    conflict_error_prefix: str,
) -> dict[Path, Provider]:
    """Select explicit overrides before rejecting ambiguous paths."""
    desired: dict[Path, Provider] = {}
    conflicts: list[str] = []

    for rel, tfs in sorted(providers.items(), key=lambda kv: str(kv[0])):
        if len(tfs) == 1:
            desired[rel] = tfs[0]
            continue

        override = path_provider_overrides.get(str(rel))
        if override:
            matches = [tf for tf in tfs if tf.owner == override]
            if len(matches) == 1:
                desired[rel] = matches[0]
                continue
            providers_list = ", ".join(sorted({tf.owner for tf in tfs}))
            conflicts.append(f"{rel} (override={override!r} not among providers: {providers_list})")
            continue

        providers_list = ", ".join(sorted({tf.owner for tf in tfs}))
        conflicts.append(f"{rel} (multiple providers: {providers_list})")

    if conflicts:
        msg = "\n".join(f"- {c}" for c in conflicts)
        raise CfgError(
            f"{conflict_error_prefix} detected between enabled owners:\n"
            f"{msg}\n\n"
            "Fix by:\n"
            "- removing one of the conflicting owners, or\n"
            "- adding an explicit path provider override in settings\n"
        )

    return desired
