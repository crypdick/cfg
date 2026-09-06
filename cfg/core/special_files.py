from __future__ import annotations

from pathlib import Path

from cfg.core.errors import CfgError
from cfg.core.models import safe_managed_relpath


class _BiMap:
    def __init__(self) -> None:
        self._forward: dict[str, str] = {}
        self._reverse: dict[str, str] = {}

    def register(self, logical: str, stored: str) -> None:
        existing = self._forward.get(logical)
        if existing and existing != stored:
            raise ValueError(f"{logical!r} already registered with stored name {existing!r}.")

        existing_rev = self._reverse.get(stored)
        if existing_rev and existing_rev != logical:
            raise ValueError(f"{stored!r} already registered with logical name {existing_rev!r}.")

        self._forward[logical] = stored
        self._reverse[stored] = logical

    def get_stored(self, logical: str, default: str | None = None) -> str | None:
        return self._forward.get(logical, default)

    def get_logical(self, stored: str, default: str | None = None) -> str | None:
        return self._reverse.get(stored, default)


_SPECIAL_FILES = _BiMap()


def register_special_filename(*, logical_name: str, stored_name: str) -> None:
    """
    Register a filename that should be "de-specialized" in the personalization repository.

    Example:
      logical_name=".gitignore", stored_name="__,gitignore"
    """
    logical_name = str(logical_name)
    stored_name = str(stored_name)

    if "/" in logical_name or "/" in stored_name:
        raise ValueError("Special filenames must be bare names (no path separators).")
    if not logical_name or not stored_name:
        raise ValueError("Special filenames must be non-empty.")

    _SPECIAL_FILES.register(logical_name, stored_name)


def logical_rel_from_storage_rel(rel: Path) -> Path:
    """
    Map an on-disk relpath inside this cfg repo back to the logical relpath that
    should be applied into target repos.
    """
    rel = Path(rel)
    parts = [_SPECIAL_FILES.get_logical(p, p) or p for p in rel.parts]
    return Path(*parts)


def storage_rel_from_logical_rel(rel: Path) -> Path:
    """
    Map a logical relpath (what we want to apply into target repos) to the on-disk
    relpath used inside this cfg repo.

    Safety:
    - Rejects `.git` path components (we never want to manage/overlay git internals).
    """
    try:
        rel = safe_managed_relpath(str(rel))
    except ValueError as e:
        raise CfgError(str(e)) from e

    parts = [_SPECIAL_FILES.get_stored(p, p) or p for p in rel.parts]
    return Path(*parts)


# Default registrations
register_special_filename(logical_name=".gitignore", stored_name="__,gitignore")
register_special_filename(logical_name=".gitattributes", stored_name="__,gitattributes")
