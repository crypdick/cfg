from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_fix(repo_root: Path, relpath: str) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "fix_future_annotations.py"
    assert script.is_file()
    return subprocess.run(
        [sys.executable, str(script), relpath],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )


def test_fix_future_annotations_noop_only_future_import(tmp_path: Path) -> None:
    p = tmp_path / "a.py"
    original = "from __future__ import annotations\n\n"
    p.write_text(original, encoding="utf-8")

    res = _run_fix(tmp_path, "a.py")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert p.read_text(encoding="utf-8") == original


def test_fix_future_annotations_noop_future_import_with_extra_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "b.py"
    original = "from __future__ import annotations\n\n\nlambda x: x\n"
    p.write_text(original, encoding="utf-8")

    res = _run_fix(tmp_path, "b.py")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert p.read_text(encoding="utf-8") == original
