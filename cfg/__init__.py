"""
Implementation package behind the `cfg` CLI. Start with `README.md` and `main.py`.
"""

from __future__ import annotations

import warnings

from beartype import BeartypeConf
from beartype.claw import beartype_this_package
from beartype.roar import BeartypeClawDecorWarning

warnings.filterwarnings("ignore", category=BeartypeClawDecorWarning)

beartype_this_package(
    conf=BeartypeConf(
        claw_is_pep526=False,
        warning_cls_on_decorator_exception=BeartypeClawDecorWarning,
    )
)

__all__: list[str] = []
