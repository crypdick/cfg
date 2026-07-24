from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from cfg.core.models import safe_repo_id_path
from cfg.repo.git import origin_url


def normalize_repo_id(origin_url: str) -> str:
    """
    Normalize a git origin URL into a stable repo id like:
      owner/repo

    Supports common formats:
    - git@github.com:owner/repo.git
    - ssh://git@github.com/owner/repo.git
    - https://github.com/owner/repo.git
    """
    origin_url = origin_url.strip()

    # SCP-like syntax: user@host:owner/repo(.git)
    m = re.match(r"^(?P<user>[^@]+)@(?P<host>[^:]+):(?P<path>.+)$", origin_url)
    if m:
        path = m.group("path")
        return _normalize_path(path)

    parsed = urlparse(origin_url)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.lstrip("/")
        return _normalize_path(path)

    # Fallback: if it looks like host/path, strip host. Otherwise treat as path already.
    if "/" in origin_url:
        first, rest = origin_url.split("/", 1)
        if "." in first:
            return _normalize_path(rest)
        return _normalize_path(origin_url)

    # Last resort: return as-is.
    return origin_url


def _normalize_path(path: str) -> str:
    path = path.strip().lstrip("/")
    path = path.removesuffix(".git")
    return path.rstrip("/")


def repo_id_for_repo(repo_root: Path) -> str | None:
    """
    Resolve a stable repo id for a working tree.

    Resolution order:
    1) git `remote.origin.url` (normalized)  [source of truth]

    If origin is missing/unparseable, return None and let callers fail loudly with remediation.
    """
    url = origin_url(repo_root)
    if url:
        cand = normalize_repo_id(url)
        try:
            safe_repo_id_path(cand)
        except ValueError:
            cand = ""

        if cand:
            return cand

    return None
