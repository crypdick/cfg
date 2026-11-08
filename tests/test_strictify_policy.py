"""Exercise installed quality checks through their public command lines."""

import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_hook(tmp_path: Path, hook_id: str, source: str) -> subprocess.CompletedProcess[str]:
    config = tomllib.loads((ROOT / "prek.toml").read_text())
    hook = next(hook for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == hook_id)
    command = shlex.split(hook["entry"])
    command = command[command.index("python") :]
    command[0] = sys.executable
    command[1] = str(ROOT / command[1])
    path = tmp_path / "test_example.py"
    path.write_text(source, encoding="utf-8")
    return subprocess.run([*command, path.name], cwd=tmp_path, capture_output=True, text=True, check=False)


def test_timeless_gate_allows_current_domain_vocabulary(tmp_path: Path) -> None:
    result = run_hook(
        tmp_path,
        "check-timeless-comments",
        '"""Protocol-compatible API."""; old = 1\n# Route to fallback provider.\n# Buffer is used to hold pending work.\n',
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_timeless_gate_reports_physical_docstring_lines(tmp_path: Path) -> None:
    result = run_hook(tmp_path, "check-timeless-comments", '"""Current API.\u2028No longer retries."""\n')
    assert result.returncode == 1, result.stdout + result.stderr
    assert "test_example.py:1:" in result.stdout


def test_installed_private_gate_uses_reviewed_package_names(tmp_path: Path) -> None:
    result = run_hook(tmp_path, "check-private-test-imports", "from cfg.internal import _secret\n")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "private '_secret'" in result.stdout
