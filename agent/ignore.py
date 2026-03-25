"""
.llamaignore — protect files/paths from agent read/write access.

Syntax is a subset of .gitignore:
  - Blank lines and # comments are ignored
  - Patterns are matched against the relative path from CWD
  - A leading / anchors to the project root (CWD)
  - Wildcards: * (any chars, no /) and ** (any chars including /)
  - A trailing / matches only directories (not currently enforced)

Example .llamaignore:
    .env
    secrets/
    **/*.key
    /config/prod.json
"""

import fnmatch
from pathlib import Path


def _load_patterns(root: Path) -> list[str]:
    p = root / ".llamaignore"
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    patterns = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line.rstrip("/"))
    return patterns


_cached_root: Path | None = None
_cached_patterns: list[str] = []


def _get_patterns() -> list[str]:
    global _cached_root, _cached_patterns
    root = Path.cwd()
    if root != _cached_root:
        _cached_root = root
        _cached_patterns = _load_patterns(root)
    return _cached_patterns


def is_ignored(path: str) -> bool:
    """Return True if path matches any .llamaignore pattern."""
    patterns = _get_patterns()
    if not patterns:
        return False

    p = Path(path)
    root = Path.cwd()

    # Normalise to relative path string
    try:
        rel = str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        # Path is outside CWD — use basename only
        rel = p.name

    for pattern in patterns:
        # Anchored patterns (start with /) match only from root
        if pattern.startswith("/"):
            anchored = pattern.lstrip("/")
            if fnmatch.fnmatch(rel, anchored):
                return True
        else:
            # Match against full relative path OR just the filename
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
                return True
            # Support ** via recursive segment matching
            if "**" in pattern:
                parts = pattern.split("**")
                if len(parts) == 2:
                    prefix, suffix = parts
                    prefix = prefix.strip("/")
                    suffix = suffix.strip("/")
                    rel_lower = rel.replace("\\", "/")
                    if prefix and not rel_lower.startswith(prefix):
                        continue
                    if suffix and not rel_lower.endswith(suffix):
                        continue
                    return True

    return False
