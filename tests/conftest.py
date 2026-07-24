"""Shared pytest fixtures for the cfg test suite."""

from __future__ import annotations

import pytest

# Git exports these location variables into hook subprocesses, so when the
# suite runs inside a git hook (git commit -> pre-commit -> pytest) they are
# present in the environment. Tests here spawn git/cfg subprocesses with an
# explicit cwd and expect them to act on that repository, not the outer one.
# Inherited GIT_DIR/GIT_INDEX_FILE/etc. override cwd and make those subprocesses
# operate on the wrong repo. Scrub the location vars so test behaviour is
# identical whether or not pytest itself was invoked from a git hook.
_LEAKED_GIT_ENV = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
)


@pytest.fixture(autouse=True)
def _scrub_leaked_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove git location vars that leak in when pytest runs from a git hook."""
    for var in _LEAKED_GIT_ENV:
        monkeypatch.delenv(var, raising=False)
