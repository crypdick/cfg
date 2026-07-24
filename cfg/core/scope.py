"""The `Scope` of a managed surface: `host` or `repo`.

cfg manages two parallel surfaces (hosts and repos) that share the same id,
prefix, and on-disk path conventions. `Scope` is the single source for them so
they cannot drift.

This module imports nothing from `cfg` and is safe to import anywhere.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class Scope(Enum):
    """A cfg-managed surface. The enum value is the bare kind string (`"host"`/`"repo"`)."""

    HOST = "host"
    REPO = "repo"

    @property
    def feature_prefix(self) -> str:
        """Owner-id prefix for this scope's features, e.g. `"host/feature/"`."""
        return f"{self.value}/feature/"

    @property
    def base_feature_id(self) -> str:
        """The implicit base feature owner id, e.g. `"host/feature/base"`."""
        return f"{self.value}/feature/base"

    def settings_dir(self, cfg_root: Path) -> Path:
        """Return the host or repo settings root."""
        return cfg_root / ("hosts" if self is Scope.HOST else "repos")

    def feature_dir(self, cfg_root: Path, short_name: str) -> Path:
        """The directory of a feature by its short name (no prefix)."""
        return cfg_root / "features" / self.value / short_name

    def feature_id(self, name: str) -> str:
        """Full owner id for a feature name, prepending the prefix if absent."""
        return name if name.startswith(self.feature_prefix) else f"{self.feature_prefix}{name}"

    def short_name(self, feature_id: str) -> str:
        """The bare feature name with this scope's prefix stripped."""
        return feature_id.removeprefix(self.feature_prefix)
