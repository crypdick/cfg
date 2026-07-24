"""Test that all modules in the cfg package are importable."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

import cfg

if TYPE_CHECKING:
    from types import ModuleType

# Modules/patterns to skip during import testing.
# - Host pyinfra workflow files execute operations at module level (not importable)
SKIP_PATTERNS = {
    "cfg.host.workflows.apply_home",
}


def _should_skip(full_name: str) -> bool:
    """Check if a module should be skipped."""
    # Skip __main__ modules (for `python -m`, not importing)
    if full_name.endswith(".__main__"):
        return True
    # Skip explicit patterns
    return full_name in SKIP_PATTERNS


def _module_exists(full_name: str) -> bool:
    """Check if a module actually exists (not just a namespace collision)."""
    try:
        spec = importlib.util.find_spec(full_name)
    except ModuleNotFoundError:
        # Namespace package collision (e.g., cfg.pyinfra vs pyinfra library)
        return False
    else:
        return spec is not None


def _import_submodules(package: str | ModuleType) -> dict[str, ModuleType]:
    """
    Import all submodules of a module, recursively, including subpackages.

    Useful for finding broken imports in a package in unit tests.

    Reference: https://stackoverflow.com/a/25562415/4212158
    """
    if isinstance(package, str):
        try:
            package = importlib.import_module(package)
        except ModuleNotFoundError as e:
            raise ModuleNotFoundError(f"Could not import package: {package}") from e

    results: dict[str, ModuleType] = {}
    for _loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = package.__name__ + "." + name

        if _should_skip(full_name):
            continue

        # Verify the module actually exists before importing
        # (avoids namespace package confusion with pyinfra library)
        if not _module_exists(full_name):
            continue

        try:
            results[full_name] = importlib.import_module(full_name)
            if is_pkg:
                results.update(_import_submodules(full_name))
        except ModuleNotFoundError as e:
            raise ModuleNotFoundError(f"Could not import module: {full_name}") from e
    return results


def test_all_modules_importable() -> None:
    """Ensure all modules in the cfg package can be imported without errors."""
    modules = _import_submodules(cfg)
    # Sanity check: we should have found a reasonable number of modules
    assert len(modules) > 10, f"Expected many modules, found only {len(modules)}"
