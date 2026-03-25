"""Code editing tools — view files with line numbers and apply exact-string edits."""

import difflib
from pathlib import Path
from agent.tools import tool
from agent.ignore import is_ignored


@tool
def view_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Read a file and display its contents with line numbers.

    Args:
        path: Path to the file to view.
        start_line: First line to show (1-indexed). Defaults to 1.
        end_line: Last line to show (inclusive). 0 means read to end of file.
    """
    if is_ignored(path):
        return f"Error: {path} is protected by .llamaignore"
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    total = len(lines)
    start = max(1, start_line) - 1  # convert to 0-indexed
    end = total if end_line <= 0 else min(end_line, total)
    slice_ = lines[start:end]
    width = len(str(end))
    numbered = "".join(
        f"{start + i + 1:>{width}}│ {line}" for i, line in enumerate(slice_)
    )
    return f"File: {path} (lines {start+1}-{end} of {total})\n{numbered}"


@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Edit a file by replacing an exact string with new content.

    The old_string must appear exactly once in the file.
    Use view_file first to confirm the exact text to replace.

    Args:
        path: Path to the file to edit.
        old_string: The exact text to find and replace (must be unique in file).
        new_string: The replacement text.
    """
    if is_ignored(path):
        return f"Error: {path} is protected by .llamaignore"
    p = Path(path)
    if not p.exists():
        # Creating a new file — old_string must be empty
        if old_string:
            return f"Error: file not found: {path}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_string, encoding="utf-8")
        return f"Created: {path} ({len(new_string)} chars)"

    original = p.read_text(encoding="utf-8")
    count = original.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {path}"
    if count > 1:
        return f"Error: old_string appears {count} times in {path} — make it more specific"

    # Write backup before modifying
    bak = p.with_suffix(p.suffix + ".bak")
    bak.write_text(original, encoding="utf-8")

    updated = original.replace(old_string, new_string, 1)
    p.write_text(updated, encoding="utf-8")

    # Return a compact unified diff as confirmation
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=2,
    )
    diff_text = "".join(list(diff)[:60])  # cap at 60 lines
    return f"Edited: {path}\n{diff_text}" if diff_text else f"Edited: {path} (no visible diff)"


def compute_diff(path: str, old_string: str, new_string: str) -> str:
    """Return a unified diff preview without writing anything (used by CLI confirmation)."""
    if is_ignored(path):
        return f"Error: {path} is protected by .llamaignore"
    p = Path(path)
    if not p.exists():
        original = ""
    else:
        original = p.read_text(encoding="utf-8")
    updated = original.replace(old_string, new_string, 1) if old_string else new_string
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    return "".join(diff) or "(no diff)"
