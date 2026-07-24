"""Single source for the Python 3.13 subprocess vfork-fastpath workaround.

pyinfra local command execution can crash under CPython 3.13's subprocess
vfork fast-path (symptom: ``TypeError: 'NoneType' object is not callable``
when ``subprocess._fork_exec`` ends up unset). We disable the fast-path and
repair ``_fork_exec`` best-effort before invoking pyinfra.

The standalone source snippet has no ``cfg`` imports, so it can be embedded in
generated ``inventory.py`` files and the ``python -c`` subprocess bootstrap.

TODO: Delete this module when Python 3.13 support ends.
"""

from __future__ import annotations

# Standalone, import-guarded statements. Safe to embed in generated files and
# `python -c` bootstraps; must not import anything from `cfg`.
VFORK_SOURCE_SNIPPET = """\
# Disable CPython 3.13 subprocess vfork fast-path (pyinfra local exec can crash;
# symptom: TypeError: 'NoneType' object is not callable when subprocess._fork_exec is None).
import subprocess
try:
    subprocess._USE_VFORK = False
    import _posixsubprocess
    subprocess._fork_exec = getattr(subprocess, '_fork_exec', None) or _posixsubprocess.fork_exec
except Exception:
    pass"""
