"""
Runtime pyinfra inventory generator.

Generates a temporary pyinfra `inventory.py` at runtime from cfg inventory,
mapping HostSettings.features to pyinfra groups and HostSettings.vars to host.data
(as `_cfg_vars` and flattened keys).

We intentionally generate a *file* because `pyinfra` CLI accepts inventory files,
and `--limit` only works meaningfully when inventory/group data exists.

Implementation detail:
pyinfra's inventory loader treats any module-level variable whose value is a list
or tuple as a group. The variable name becomes the group name.

To support arbitrary cfg group names (including dashes), we inject them with
`globals().update({...})` rather than using Python identifiers.
"""

from __future__ import annotations

import os
import pprint
import shutil
import tempfile
from pathlib import Path
from typing import Any

from cfg.core.inventory import Inventory
from cfg.core.models import dedupe_preserve_order
from cfg.core.owners import resolve_host_owner_ids_for_host
from cfg.core.protocols import HostSettingsLike
from cfg.deploys.host_data import CFG_HOST_NAME, CFG_HOST_OWNER_IDS, CFG_ROOT
from cfg.pyinfra._vfork import VFORK_SOURCE_SNIPPET


def _jsonish(value: Any) -> Any:
    """
    Convert values into a Python-literal-friendly structure for embedding into an
    inventory file.

    This avoids issues like `PosixPath(...)` reprs that would require imports to
    evaluate.
    """

    if value is None or isinstance(value, str | int | float | bool):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _jsonish(v) for k, v in value.items()}

    if isinstance(value, list | tuple | set):
        return [_jsonish(v) for v in value]

    # Pydantic models, etc.
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _jsonish(model_dump())
        except (TypeError, ValueError):
            return str(value)

    return str(value)


def _host_data(*, settings: HostSettingsLike, cfg_root: Path, cfg_inventory: Inventory) -> dict[str, Any]:
    data: dict[str, Any] = {}

    data[CFG_HOST_NAME] = str(settings.name)
    data[CFG_HOST_OWNER_IDS] = resolve_host_owner_ids_for_host(
        cfg_root=cfg_root,
        cfg_inventory=cfg_inventory,
        host_settings=settings,  # pyright: ignore[reportArgumentType] — HostSettingsLike is duck-type compatible; callers always pass HostSettings
    )

    # Commonly useful inventory material for future deploys (safe strings).
    if settings.repos:
        data["_cfg_repos"] = {str(repo_id): str(path) for repo_id, path in settings.repos.items()}

    vars_jsonish = _jsonish(settings.vars) or {}
    if not isinstance(vars_jsonish, dict):
        # If the user somehow put a non-dict here, preserve it but don't flatten.
        data["_cfg_vars"] = vars_jsonish
    else:
        data["_cfg_vars"] = dict(vars_jsonish)
        # Flatten vars to top-level keys for ergonomic `host.data.<key>`.
        for k, v in vars_jsonish.items():
            key = str(k)
            if key in data:
                continue
            data[key] = v

    # Connection settings (mirrors pyinfra's SSH connector data keys).
    if settings.ssh:
        if settings.ssh.host:
            data["ssh_hostname"] = str(settings.ssh.host)
        if settings.ssh.user:
            data["ssh_user"] = str(settings.ssh.user)
        if settings.ssh.port:
            data["ssh_port"] = int(settings.ssh.port)

    return data


def _add_host_to_group(groups: dict[str, list[str]], group: str, host_name: str) -> None:
    g = str(group).strip()
    if not g:
        return
    # pyinfra inventory loader ignores leading underscores.
    if g.startswith("_"):
        return
    groups.setdefault(g, []).append(host_name)


def build_groups(
    *,
    cfg_inventory: Inventory,
    cfg_root: Path,
    current_host_for_local: str | None,
    include_local: bool,
) -> dict[str, list[Any]]:
    """
    Build a pyinfra inventory "groups" dict suitable for embedding into an
    inventory file. Values are either:
    - list of hosts (string or (host, data) tuples)
    - tuple (hosts, data) (not currently used here)
    """

    # We'll store per-host data in the `all` group as (name, data) tuples.
    all_hosts: list[Any] = []

    # Additional groups: group_name -> [host_name, ...]
    groups: dict[str, list[str]] = {}

    # Runtime inventory only exposes group membership; owner resolution is explicit via inventory owners.

    # Remote/SSH hosts (cfg inventory names).
    for loaded in cfg_inventory.hosts.values():
        h = loaded.settings
        name = str(h.name)
        data = _host_data(settings=h, cfg_root=cfg_root, cfg_inventory=cfg_inventory)
        data[CFG_ROOT] = str(cfg_root)
        all_hosts.append((name, data))

        for g in list(h.features or []):
            _add_host_to_group(groups, g, name)

    # Optional local host alias with the current host's data/groups.
    if include_local:
        local_data: dict[str, Any] = {CFG_HOST_NAME: str(current_host_for_local or "")}
        local_settings = cfg_inventory.host_get(current_host_for_local) if current_host_for_local else None
        if local_settings:
            local_data = _host_data(settings=local_settings, cfg_root=cfg_root, cfg_inventory=cfg_inventory)

        local_name = "@local"
        local_data[CFG_ROOT] = str(cfg_root)

        # Allow callers to explicitly augment local host owner ids (eg `cfg repo apply --ensure-host`).
        extra_raw = (os.environ.get("CFG_EXTRA_HOST_OWNER_IDS") or "").strip()
        if extra_raw:
            extra = [s.strip() for s in extra_raw.split(",") if s.strip()]
            if extra:
                existing = local_data.get(CFG_HOST_OWNER_IDS) or []
                if isinstance(existing, list):
                    local_data[CFG_HOST_OWNER_IDS] = dedupe_preserve_order([*map(str, existing), *extra])

        all_hosts.append((local_name, local_data))

        if local_settings:
            for g in list(local_settings.features or []):
                _add_host_to_group(groups, g, local_name)

    # Build final dict with deterministic ordering and de-duped host lists.
    out: dict[str, list[Any]] = {"all": all_hosts}
    for group_name in sorted(groups):
        out[group_name] = dedupe_preserve_order(groups[group_name])

    return out


def write_inventory_file(
    *,
    groups: dict[str, Any],
    header_lines: list[str] | None = None,
) -> tuple[Path, Path]:
    """
    Write a pyinfra inventory.py file for the given groups into a temp directory.

    Returns (inventory_path, temp_dir_path) so callers can clean up safely.
    """

    tmpdir = Path(tempfile.mkdtemp(prefix="cfg_pyinfra_"))
    inv_path = tmpdir / "inventory.py"

    # Use pprint for stable/valid Python literals.
    rendered = pprint.pformat(groups, width=110, sort_dicts=False)

    header = header_lines or [
        "# Generated by cfg. DO NOT EDIT.",
        "# ruff: noqa",
    ]

    inv_path.write_text(
        "\n".join(
            [
                *header,
                "",
                VFORK_SOURCE_SNIPPET,
                "",
                f"GROUPS = {rendered}",
                "globals().update(GROUPS)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return inv_path, tmpdir


def write_runtime_inventory(
    *,
    cfg_root: Path,
    cfg_inventory: Inventory,
    current_host_for_local: str | None,
    include_local: bool,
) -> tuple[Path, Path]:
    """
    Write a generated inventory.py into a temporary directory.

    Returns (inventory_path, temp_dir_path) so callers can clean up safely.
    """

    groups = build_groups(
        cfg_inventory=cfg_inventory,
        cfg_root=cfg_root,
        current_host_for_local=current_host_for_local,
        include_local=include_local,
    )
    return write_inventory_file(
        groups=groups,
        header_lines=[
            "# Generated by cfg. DO NOT EDIT.",
            "# Source: cfg host settings and features",
            "# Purpose: enable pyinfra groups + host.data via `--limit`.",
            "# ruff: noqa",
        ],
    )


def cleanup_runtime_inventory(tmpdir: Path) -> None:
    shutil.rmtree(tmpdir, ignore_errors=True)
