from __future__ import annotations

from pathlib import Path

import pytest

from cfg.core import special_files as sf
from cfg.core.errors import CfgError
from cfg.core.special_files import logical_rel_from_storage_rel, storage_rel_from_logical_rel


def test_special_files_maps_gitignore_and_gitattributes() -> None:
    assert storage_rel_from_logical_rel(Path(".gitignore")) == Path("__,gitignore")
    assert storage_rel_from_logical_rel(Path("a/.gitattributes")) == Path("a/__,gitattributes")
    assert logical_rel_from_storage_rel(Path("a/__,gitattributes")) == Path("a/.gitattributes")


def test_special_files_blocks_dot_git_components() -> None:
    with pytest.raises(CfgError, match="Refusing to manage"):
        storage_rel_from_logical_rel(Path(".git/config"))


def test_register_special_filename_validation_and_conflicts() -> None:
    # Snapshot global registries (register_special_filename mutates module globals).
    bimap = sf._SPECIAL_FILES
    old_fwd = dict(bimap._forward)
    old_rev = dict(bimap._reverse)
    try:
        with pytest.raises(ValueError, match="no path separators"):
            sf.register_special_filename(logical_name="a/b", stored_name="x")
        with pytest.raises(ValueError, match="non-empty"):
            sf.register_special_filename(logical_name="", stored_name="x")

        # Conflict: same logical name, different stored name.
        with pytest.raises(ValueError, match="already registered"):
            sf.register_special_filename(logical_name=".gitignore", stored_name="different")

        # Conflict: stored name already used for different logical name.
        with pytest.raises(ValueError, match="already registered"):
            sf.register_special_filename(logical_name="other", stored_name="__,gitignore")
    finally:
        bimap._forward.clear()
        bimap._forward.update(old_fwd)
        bimap._reverse.clear()
        bimap._reverse.update(old_rev)
