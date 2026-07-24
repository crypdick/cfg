from __future__ import annotations

import tomli_w

from cfg.core.owners.models import FeatureManifest


def feature_manifest_to_bytes(manifest: FeatureManifest) -> bytes:
    """Serialize the small user-authored feature metadata schema."""
    return tomli_w.dumps(manifest.model_dump(mode="json"), multiline_strings=False).encode("utf-8")
