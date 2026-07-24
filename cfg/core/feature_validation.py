"""
Shared validation functions for feature operations.

These validators are used by both host and repo feature commands to ensure
consistent error messages and fail-fast behavior.
"""

from __future__ import annotations

from cfg.core.context import CfgContext
from cfg.core.errors import CfgError
from cfg.core.owners.manifest_io import load_owner_manifest_index
from cfg.core.scope import Scope


def require_feature_exists_in_manifest(
    ctx: CfgContext,
    feature_id: str,
    scope: Scope,
) -> None:
    """
    Validate that a feature exists in the manifest index.

    Use this before adding a feature to a host/repo, or when removing
    to ensure the feature ID is valid.

    Raises:
        CfgError: If the feature doesn't exist, with helpful suggestions.
    """
    idx = load_owner_manifest_index(ctx.root)
    prefix = scope.feature_prefix

    owner_id = scope.feature_id(feature_id)
    if owner_id not in idx:
        short_name = feature_id
        available = sorted(k for k in idx if k.startswith(prefix))
        available_short = [scope.short_name(k) for k in available]

        raise CfgError(
            f"Feature not found: {short_name}\n\n"
            f"Available {scope.value} features: {', '.join(available_short)}\n\n"
            f"To create a new feature:\n"
            f"  cfg {scope.value} feature create {short_name}"
        )


def require_feature_not_exists_in_manifest(
    ctx: CfgContext,
    feature_id: str,
    scope: Scope,
) -> None:
    """
    Validate that a feature does NOT exist in the manifest index.

    Use this before creating a new feature to prevent overwriting.

    Raises:
        CfgError: If the feature already exists.
    """
    idx = load_owner_manifest_index(ctx.root)

    owner_id = scope.feature_id(feature_id)
    if owner_id in idx:
        short_name = feature_id
        feature_path = scope.feature_dir(ctx.root, short_name)
        raise CfgError(
            f"Feature already exists: {short_name}\n"
            f"Path: {feature_path}\n\n"
            f"To modify the feature, edit feature.toml directly:\n"
            f"  {feature_path / 'feature.toml'}"
        )
