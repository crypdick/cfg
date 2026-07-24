from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cfg.core.models import HostSettings, RepoSettings, safe_relpath, safe_repo_id_path


def test_safe_relpath_rejects_absolute_and_dotdot() -> None:
    with pytest.raises(ValueError, match="Unsafe"):
        safe_relpath("/abs/path")
    with pytest.raises(ValueError, match="Unsafe"):
        safe_relpath("../up")
    with pytest.raises(ValueError, match="Unsafe"):
        safe_relpath("a/../b")


def test_safe_repo_id_path_requires_owner_repo() -> None:
    assert safe_repo_id_path("owner/repo") == Path("owner/repo")
    with pytest.raises(ValueError, match="owner/repo"):
        safe_repo_id_path("just-one-segment")
    with pytest.raises(ValueError, match="Unsafe"):
        safe_repo_id_path("../owner/repo")


def test_host_settings_dedupes_features_preserving_order() -> None:
    h = HostSettings(name="h1", features=["desktop", "desktop", ""])
    assert h.features == ["desktop"]

    with pytest.raises(ValidationError, match="Do not configure base explicitly"):
        HostSettings(name="h1", features=["base"])


def test_repo_settings_dedupes_features_and_validates_repo_id() -> None:
    r = RepoSettings(id="owner/repo", features=["uv", "uv", ""])
    assert r.features == ["uv"]

    with pytest.raises(ValidationError):
        RepoSettings(id="not-valid", features=[])


def test_repo_settings_rejects_empty_provider_override() -> None:
    with pytest.raises(ValidationError, match="Empty provider"):
        RepoSettings(id="owner/repo", path_provider_overrides={"a.txt": " "})


def test_host_settings_rejects_empty_repo_id_key() -> None:
    with pytest.raises(ValidationError, match="Repo id key must be non-empty"):
        HostSettings(name="h1", repos={"": Path("/tmp/x")})


def test_safe_relpath_allows_cfg_workflow_paths() -> None:
    assert safe_relpath("cfg/host/workflows/setup_i3.py") == Path("cfg/host/workflows/setup_i3.py")
