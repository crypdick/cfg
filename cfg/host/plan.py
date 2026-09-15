"""Plan stale host cleanup and record state after successful deployment."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.ids import HostName, OwnerId
from cfg.core.models import HostStateManifest, ManagedPathState
from cfg.core.state import write_host_state
from cfg.host.fs import HOST_HOME_PROVIDER
from cfg.host.managed_home import HomePlan, managed_home_roots


@dataclass(frozen=True)
class RemoveHostPath:
    rel: Path
    expected_kind: str
    expected_digest: str | None = None
    expected_target: Path | None = None


@dataclass(frozen=True)
class HostApplyPlan:
    cfg_root: Path
    home: Path
    host: HostName
    outputs: HomePlan
    removals: tuple[RemoveHostPath, ...]


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _link_target(path: Path) -> Path:
    target = path.readlink()
    if not target.is_absolute():
        target = path.parent / target
    return target.resolve(strict=False)


def _is_cfg_link(path: Path, roots: list[Path]) -> bool:
    if not path.is_symlink():
        return False
    target = _link_target(path)
    return any(target.is_relative_to(root) for root in roots)


def _validate_removal(removal: RemoveHostPath, *, home: Path, conflicts: list[str]) -> None:
    destination = home / removal.rel
    if not destination.exists() and not destination.is_symlink():
        return
    if removal.expected_kind == "overlay":
        if not destination.is_symlink() or removal.expected_target is None:
            conflicts.append(f"{removal.rel} (stale overlay is no longer a cfg-owned symlink)")
        elif _link_target(destination) != removal.expected_target.resolve(strict=False):
            conflicts.append(f"{removal.rel} (stale overlay points somewhere else)")
        return
    if destination.is_symlink() or not destination.is_file():
        conflicts.append(f"{removal.rel} (stale generated output is not a regular file)")
    elif removal.expected_digest is None or _digest_file(destination) != removal.expected_digest:
        conflicts.append(f"{removal.rel} (stale generated output changed after cfg last applied it)")


def build_host_apply_plan(
    *,
    cfg_root: Path,
    home: Path,
    host: HostName,
    outputs: HomePlan,
    previous_state: HostStateManifest,
) -> HostApplyPlan:
    """Build complete stale-removal plan without changing home."""
    desired_kinds = dict.fromkeys(outputs.desired, "overlay")
    desired_kinds.update(dict.fromkeys(outputs.generated, "generated"))
    desired_sources = {rel: file.src.resolve() for rel, file in outputs.desired.items()}
    removals: list[RemoveHostPath] = []

    for raw_rel, prior in sorted(previous_state.managed.items()):
        rel = Path(raw_rel)
        desired_kind = desired_kinds.get(rel)
        unchanged_overlay = (
            desired_kind == "overlay"
            and prior.kind == "overlay"
            and prior.source is not None
            and Path(prior.source).resolve(strict=False) == desired_sources[rel]
        )
        if unchanged_overlay or (desired_kind == "generated" and prior.kind == "generated"):
            continue
        if prior.kind == "overlay":
            if prior.source is None or not Path(prior.source).is_absolute():
                raise CfgError(f"{rel} (stale overlay has no recorded absolute source)")
            removals.append(
                RemoveHostPath(
                    rel=rel,
                    expected_kind="overlay",
                    expected_target=Path(prior.source),
                )
            )
        else:
            removals.append(
                RemoveHostPath(
                    rel=rel,
                    expected_kind=prior.kind,
                    expected_digest=prior.digest,
                )
            )

    planned_rels = {removal.rel for removal in removals}
    roots = managed_home_roots(cfg_root)
    for rel in outputs.generated:
        destination = home / rel
        if rel not in planned_rels and _is_cfg_link(destination, roots):
            removals.append(
                RemoveHostPath(
                    rel=rel,
                    expected_kind="overlay",
                    expected_target=_link_target(destination),
                )
            )

    plan = HostApplyPlan(
        cfg_root=cfg_root.resolve(),
        home=home.resolve(),
        host=host,
        outputs=outputs,
        removals=tuple(removals),
    )
    _validate_plan(plan)
    return plan


def _validate_plan(plan: HostApplyPlan) -> None:
    conflicts: list[str] = []
    for removal in plan.removals:
        _validate_removal(removal, home=plan.home, conflicts=conflicts)
    if conflicts:
        details = "\n".join(f"- {conflict}" for conflict in sorted(set(conflicts)))
        raise CfgError(
            "Host apply plan has conflicts in home:\n"
            f"{details}\n\nResolve conflicting paths, then run `cfg host apply` again."
        )


def apply_host_cleanup(plan: HostApplyPlan) -> int:
    """Apply validated stale removals before pyinfra runs."""
    _validate_plan(plan)
    changed = 0
    for removal in plan.removals:
        destination = plan.home / removal.rel
        if destination.exists() or destination.is_symlink():
            destination.unlink()
            changed += 1
    return changed


def capture_host_state(plan: HostApplyPlan) -> Path:
    """Inspect actual outputs and persist state after successful pyinfra completion."""
    managed: dict[str, ManagedPathState] = {}
    conflicts: list[str] = []
    host_owner = OwnerId(f"host/{plan.host}")

    for rel, file in sorted(plan.outputs.desired.items(), key=lambda item: item[0].as_posix()):
        destination = plan.home / rel
        source = file.src.resolve()
        if not destination.is_symlink() or _link_target(destination) != source:
            conflicts.append(f"{rel} (expected deployed cfg symlink is missing or changed)")
            continue
        owner = host_owner if file.owner == HOST_HOME_PROVIDER else OwnerId(file.owner)
        managed[rel.as_posix()] = ManagedPathState(
            kind="overlay",
            owner=owner,
            digest=_digest_file(source),
            source=str(source),
        )

    for rel, target in sorted(plan.outputs.generated.items(), key=lambda item: item[0].as_posix()):
        destination = plan.home / rel
        if destination.is_symlink() or not destination.is_file():
            conflicts.append(f"{rel} (declared generated output is missing or not a regular file)")
            continue
        managed[rel.as_posix()] = ManagedPathState(
            kind="generated",
            owner=target.owner,
            digest=_digest_file(destination),
        )

    if conflicts:
        details = "\n".join(f"- {conflict}" for conflict in conflicts)
        raise CfgError(f"Host apply completed but managed output verification failed:\n{details}")
    return write_host_state(HostStateManifest(host=plan.host, managed=managed))


def format_host_cleanup(plan: HostApplyPlan) -> list[str]:
    return [f"- remove stale {item.expected_kind}: ~/{item.rel}" for item in plan.removals]
