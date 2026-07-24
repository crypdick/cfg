"""Shared rendering for the host/repo "managed files" reports.

Both `cfg host managed` and `cfg repo settings` print the same three sections
(linked / mirrored / generated) of `relpath -> (owner, src)` entries. This
module owns that rendering and the generated-template-source derivation so the
two command surfaces stay identical instead of drifting apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cfg.core.cli_logic_utils import format_sourced_paths_list
from cfg.core.owners import owner_id_to_dir
from cfg.render.generated import GeneratedTarget


@dataclass(frozen=True)
class GeneratedSource:
    """A generated target paired with the template file that produces it (for reporting)."""

    owner: str
    src: Path


def generated_sources(
    *, cfg_root: Path, desired_targets: Mapping[Path, GeneratedTarget]
) -> dict[Path, GeneratedSource]:
    """Map resolved generated targets to the `.j2` template sources that render them."""
    out: dict[Path, GeneratedSource] = {}
    for rel, target in sorted(desired_targets.items(), key=lambda kv: kv[0].as_posix()):
        src = owner_id_to_dir(cfg_root, target.owner) / "render" / "templates" / f"{rel.as_posix()}.j2"
        out[rel] = GeneratedSource(owner=target.owner, src=src)
    return out


def _format_section(*, header: str, desired: Mapping[Path, object]) -> list[str]:
    lines = [f"{header}:"]
    body = format_sourced_paths_list(header="", desired=desired)
    lines.extend(body or ["- (none)"])
    return lines


def format_managed_sections(
    *,
    linked: Mapping[Path, object],
    mirrored: Mapping[Path, object],
    generated: Mapping[Path, object],
) -> list[str]:
    """Render the linked/mirrored/generated report block (blank-line separated)."""
    lines = _format_section(header="linked", desired=linked)
    lines.append("")
    lines.extend(_format_section(header="mirrored", desired=mirrored))
    lines.append("")
    lines.extend(_format_section(header="generated", desired=generated))
    return lines
