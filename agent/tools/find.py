"""File search tools — find files by name pattern and search content by regex."""

import fnmatch
import re
from pathlib import Path

from agent.tools import tool

_SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"}


@tool
def glob_files(pattern: str, root: str = "") -> str:
    """Find files matching a glob pattern under a directory.

    Args:
        pattern: Glob pattern such as '**/*.py', 'src/*.ts', or '*.md'.
        root: Directory to search in. Empty means current working directory.
    """
    base = Path(root).expanduser().resolve() if root else Path.cwd()
    if not base.exists():
        return f"Error: directory not found: {base}"

    matches: list[Path] = []
    try:
        for p in base.rglob(pattern.lstrip("**/")):
            if any(skip in p.parts for skip in _SKIP_DIRS):
                continue
            matches.append(p)
    except Exception as e:
        return f"Error: {e}"

    if not matches:
        return f"No files matching '{pattern}' under {base}"

    lines = [str(p.relative_to(base)) for p in sorted(matches)[:200]]
    result = "\n".join(lines)
    if len(matches) > 200:
        result += f"\n... ({len(matches)} total, showing first 200)"
    return result


@tool
def search_files(pattern: str, path: str = "", file_glob: str = "", max_results: int = 50) -> str:
    """Search for a regex pattern inside files and return matching lines with context.

    Args:
        pattern: Regular expression to search for (e.g. 'def run_setup', 'import openai').
        path: File or directory to search. Empty means current working directory.
        file_glob: Filter files by glob pattern (e.g. '*.py', '*.ts'). Empty means all text files.
        max_results: Maximum number of matching lines to return.
    """
    base = Path(path).expanduser().resolve() if path else Path.cwd()

    if base.is_file():
        candidates = [base]
    elif base.is_dir():
        glob = file_glob if file_glob else "*"
        candidates = [
            p for p in base.rglob(glob)
            if p.is_file() and not any(s in p.parts for s in _SKIP_DIRS)
        ]
    else:
        return f"Error: path not found: {base}"

    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex: {e}"

    results: list[str] = []
    for filepath in sorted(candidates):
        try:
            text = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                rel = filepath.relative_to(base) if filepath != base else filepath
                results.append(f"{rel}:{lineno}: {line.rstrip()}")
                if len(results) >= max_results:
                    results.append(f"... (stopped at {max_results} results)")
                    return "\n".join(results)

    if not results:
        return f"No matches for '{pattern}'"
    return "\n".join(results)
