from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cfg.core.scope import Scope

NO_CHANGE_ALREADY_PRESENT = "no change (already present)."
NO_CHANGE_NOT_PRESENT = "no change (not present)."
NO_CHANGE_NOT_MANAGED = "no change (not managed)."


def normalize_feature_name(feature: str, scope: Scope, *, allow_base: bool = False) -> str:
    """Validate and return a scope-local short feature name."""
    f = str(feature).strip()
    if not f:
        raise ValueError("Feature cannot be empty")
    if f.startswith("_"):
        # pyinfra ignores underscore-prefixed groups; enforce for consistency.
        raise ValueError("Feature cannot start with '_' (pyinfra ignores underscore-prefixed groups)")

    from cfg.core.models import safe_relpath

    path = safe_relpath(f)
    if len(path.parts) != 1:
        raise ValueError(f"Use a short {scope.value} feature name without a scope prefix, got: {feature!r}")
    if not allow_base and f == "base":
        raise ValueError("Do not configure base; it is always enabled implicitly.")
    return f


def format_features_list(features: Iterable[str]) -> list[str]:
    lines = ["features:"]
    lines.extend(f"- {t}" for t in features or [])
    return lines


def format_sourced_paths_list(*, header: str, desired: Any) -> list[str]:
    """
    Format a mapping of relpath -> object with `.owner` and `.src` attrs.

    This is intentionally typed loosely (Any) because it's CLI formatting glue and
    should stay decoupled from internal plan/model types.
    """
    if not desired:
        return []

    lines: list[str] = []
    if header:
        lines.append(f"{header}:")
    for rel, tf in sorted(desired.items(), key=lambda kv: str(kv[0])):
        owner = getattr(tf, "owner", "?")
        src = getattr(tf, "src", "?")
        lines.append(f"- {rel}  (from {owner}: {src})")
    return lines


_INVALID_REPO_KV = "Invalid --repo value (expected 'owner/repo=/abs/path')"


def parse_repo_kv(raw: str) -> tuple[str, Path]:
    """
    Parse a `--repo` CLI value of the form: `owner/repo=/abs/path`.

    Raises ValueError with the existing stable error message on invalid input.
    """
    s = str(raw).strip()
    if not s or "=" not in s:
        raise ValueError(_INVALID_REPO_KV)
    repo_id, repo_path = s.split("=", 1)
    repo_id = repo_id.strip()
    repo_path = repo_path.strip()
    if not repo_id or not repo_path:
        raise ValueError(_INVALID_REPO_KV)
    return repo_id, Path(repo_path).expanduser().resolve()
