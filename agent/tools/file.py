"""File system tools."""

import os
from pathlib import Path
from agent.tools import tool
from agent.ignore import is_ignored


@tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Absolute or relative path to the file to read.
    """
    if is_ignored(path):
        return f"Error: {path} is protected by .llamaignore"
    return Path(path).read_text(encoding="utf-8")


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it if it does not exist.

    Args:
        path: Absolute or relative path of the file to write.
        content: Text content to write into the file.
    """
    if is_ignored(path):
        return f"Error: {path} is protected by .llamaignore"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written {len(content)} characters to {path}"


@tool
def list_dir(path: str) -> str:
    """List files and directories at a path.

    Args:
        path: Directory path to list. Defaults to current directory.
    """
    p = Path(path) if path else Path(".")
    if not p.exists():
        return f"Error: path does not exist: {path}"
    entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
    lines = []
    for entry in entries:
        prefix = "📄" if entry.is_file() else "📁"
        lines.append(f"{prefix} {entry.name}")
    return "\n".join(lines) if lines else "(empty directory)"


@tool
def make_dir(path: str) -> str:
    """Create a directory (and any missing parents).

    Args:
        path: Directory path to create.
    """
    Path(path).mkdir(parents=True, exist_ok=True)
    return f"Directory created: {path}"


@tool
def delete_file(path: str) -> str:
    """Delete a file.

    Args:
        path: Path of the file to delete.
    """
    if is_ignored(path):
        return f"Error: {path} is protected by .llamaignore"
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"
    p.unlink()
    return f"Deleted: {path}"
