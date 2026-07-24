from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_check(repo_root: Path, relpath: str) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "prek_hooks" / "check_timeless_comments.py"
    assert script.is_file()
    return subprocess.run(
        [sys.executable, str(script), relpath],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )


def test_timeless_comments_ignores_non_docstring_multiline_strings(tmp_path: Path) -> None:
    source = tmp_path / "fixture.py"
    source.write_text(
        'PAYLOAD = """\nfixture text\n"""\nold = "domain value"\n',
        encoding="utf-8",
    )

    result = _run_check(tmp_path, source.name)

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_timeless_comments_checks_real_comments_and_docstrings(tmp_path: Path) -> None:
    source = tmp_path / "documented.py"
    source.write_text(
        '"""Legacy adapter."""\n\nvalue = 1  # old behavior\n',
        encoding="utf-8",
    )

    result = _run_check(tmp_path, source.name)

    assert result.returncode == 1
    assert result.stdout.count("documented.py:") == 2
    assert r"\blegacy\b" in result.stdout
    assert r"\bold\b" in result.stdout


def test_timeless_comments_honors_narrow_exemption(tmp_path: Path) -> None:
    source = tmp_path / "exempt.py"
    source.write_text("value = 1  # fallback is domain vocabulary  # temporal-ok\n", encoding="utf-8")

    result = _run_check(tmp_path, source.name)

    assert result.returncode == 0, (result.stdout, result.stderr)
