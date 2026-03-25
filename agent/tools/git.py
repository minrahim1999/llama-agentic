"""Git tools — read-only queries and confirmation-gated commit."""

import subprocess
from pathlib import Path
from agent.tools import tool


def _git(*args: str, cwd: str | None = None) -> str:
    """Run a git command and return combined stdout/stderr."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd or Path.cwd(),
    )
    out = result.stdout.strip()
    err = result.stderr.strip()
    if result.returncode != 0:
        return f"Error (exit {result.returncode}): {err or out}"
    return out or "(no output)"


@tool
def git_status() -> str:
    """Show the working tree status (staged, unstaged, and untracked files)."""
    return _git("status", "--short", "--branch")


@tool
def git_diff(staged: bool = False, path: str = "") -> str:
    """Show uncommitted changes as a unified diff.

    Args:
        staged: If true, show staged (index) diff; otherwise show unstaged working-tree diff.
        path: Limit diff to a specific file or directory. Empty means whole repo.
    """
    args = ["diff"]
    if staged:
        args.append("--cached")
    args.extend(["--stat", "--patch", "--no-color"])
    if path:
        args.extend(["--", path])
    return _git(*args)


@tool
def git_log(n: int = 10, oneline: bool = True) -> str:
    """Show recent git commit history.

    Args:
        n: Number of commits to show.
        oneline: If true, show one line per commit; otherwise show full log.
    """
    args = ["log", f"-{n}", "--no-color"]
    if oneline:
        args.append("--oneline")
    return _git(*args)


@tool
def git_commit(message: str, add_all: bool = False) -> str:
    """Create a git commit.

    Args:
        message: Commit message.
        add_all: If true, stage all tracked modified files (git add -u) before committing.
    """
    if add_all:
        stage = _git("add", "-u")
        if stage.startswith("Error"):
            return stage
    return _git("commit", "-m", message)


@tool
def git_add(paths: str) -> str:
    """Stage files for the next git commit.

    Args:
        paths: Space-separated file paths or patterns to stage (e.g. 'src/main.py' or '.' for all).
    """
    args = ["add"] + paths.split()
    return _git(*args)


@tool
def git_branch(name: str = "", checkout: bool = False, create: bool = False) -> str:
    """List, create, or switch git branches.

    Args:
        name: Branch name. Empty means list all branches.
        checkout: If true, switch to the branch.
        create: If true, create the branch (use with checkout=true to create and switch).
    """
    if not name:
        return _git("branch", "-a")
    if create and checkout:
        return _git("checkout", "-b", name)
    if create:
        return _git("branch", name)
    if checkout:
        return _git("checkout", name)
    return _git("branch", "--list", name)
