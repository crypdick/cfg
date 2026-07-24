"""
Implementation package behind the `cfg` CLI. Start with `README.md` and `main.py`.
"""

from __future__ import annotations

# Enable runtime type checking across the `cfg` package.
from beartype.claw import beartype_this_package

beartype_this_package()

__all__: list[str] = []
