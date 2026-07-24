from __future__ import annotations

import sys
from pathlib import Path


def _is_docstring_start(line: str) -> bool:
    s = line.lstrip()
    return s.startswith(('"""', "'''"))


def _docstring_end_idx(lines: list[str], start_idx: int) -> int | None:
    """
    If `lines[start_idx]` begins a triple-quoted string, return the line index
    of the line *after* the closing delimiter. Otherwise return None.
    """
    first = lines[start_idx]
    s = first.lstrip()
    if s.startswith('"""'):
        delim = '"""'
    elif s.startswith("'''"):
        delim = "'''"
    else:
        return None

    # Single-line docstring: opening and closing on same line.
    if s.count(delim) >= 2:
        return start_idx + 1

    for i in range(start_idx + 1, len(lines)):
        if delim in lines[i]:
            return i + 1
    return None


def _find_insertion_point(lines: list[str]) -> int:
    """
    Return the line index where `from __future__ import annotations` should live:
    after shebang/encoding, after an optional uv `# /// script` metadata block,
    and after an optional module docstring.
    """
    i = 0
    # shebang
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    # encoding cookie (PEP 263) can be on 1st or 2nd line (after shebang)
    if i < len(lines) and "coding" in lines[i] and lines[i].lstrip().startswith("#"):
        i += 1
    # blank lines after shebang/encoding
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    # uv PEP-723 script metadata block:
    #   # /// script
    #   # ...
    #   # ///
    if i < len(lines) and lines[i].strip() == "# /// script":
        i += 1
        while i < len(lines):
            if lines[i].strip() == "# ///":
                i += 1
                break
            i += 1
        # blank lines after block
        while i < len(lines) and lines[i].strip() == "":
            i += 1
    # optional module docstring
    if i < len(lines) and _is_docstring_start(lines[i]):
        end = _docstring_end_idx(lines, i)
        if end is not None:
            i = end
        # keep trailing blank line(s) after docstring
        while i < len(lines) and lines[i].strip() == "":
            i += 1
    return i


def _detect_newline_style(raw: str) -> str:
    """
    Detect newline style for writing.

    We only preserve CRLF when the file is *pure* CRLF. If the file contains any
    bare LF newlines, we write using LF to avoid converting a mixed-newline file
    into "all CRLF" (surprising/noisy diffs).
    """
    crlf = raw.count("\r\n")
    # Count bare LFs (not part of CRLF sequences).
    lf = raw.count("\n") - crlf
    return "\r\n" if crlf and lf == 0 else "\n"


def _fix_file(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    nl = _detect_newline_style(raw)
    text = raw.replace("\r\n", "\n")
    lines = text.splitlines(keepends=True)

    target = "from __future__ import annotations\n"

    # Find existing import line (exact match ignoring leading/trailing whitespace)
    existing_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "from __future__ import annotations":
            existing_idx = i
            break
    if existing_idx is None:
        return False

    # If it's already at the correct insertion point (after shebang/encoding/uv-block/docstring),
    # treat as a no-op even if there are extra blank lines after it.
    if existing_idx == _find_insertion_point(lines):
        return False

    # Remove the existing line (do not normalize whitespace beyond what's required).
    lines.pop(existing_idx)

    insert_at = _find_insertion_point(lines)
    lines.insert(insert_at, target)
    # Ensure there's at least one blank line after future import if the next line is non-blank.
    if insert_at + 1 < len(lines) and lines[insert_at + 1].strip() != "":
        lines.insert(insert_at + 1, "\n")

    new = "".join(lines)
    if nl == "\r\n":
        new = new.replace("\n", "\r\n")
    if new == raw:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def _iter_target_files(repo_root: Path, argv: list[str]) -> list[Path]:
    # When invoked by prek, file paths are passed as argv.
    # We only touch the provided files to avoid repo-wide churn.
    if argv:
        out: list[Path] = []
        for raw in argv:
            p = (repo_root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
            try:
                p.relative_to(repo_root)
            except ValueError:
                continue
            out.append(p)
        return out

    # Manual invocation fallback: scan the repo for python files.
    return list(repo_root.rglob("*.py"))


def main(argv: list[str]) -> int:
    repo_root = Path.cwd().resolve()

    changed: list[Path] = []
    for p in _iter_target_files(repo_root, argv):
        if not p.exists() or not p.is_file():
            continue
        if p.suffix != ".py":
            continue
        rel_parts = p.relative_to(repo_root).parts
        if any(part in {".git", ".venv", "__pycache__", ".cfg", "build"} for part in rel_parts):
            continue
        if p.is_symlink():
            continue
        try:
            if _fix_file(p):
                changed.append(p)
        except Exception as e:
            print(f"[fix_future_annotations] error: {p}: {e}")
            return 2

    if changed:
        print("[fix_future_annotations] updated files:")
        for p in changed:
            print(f"- {p}")
        # Non-zero so prek stops and the user can re-run and re-stage.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
