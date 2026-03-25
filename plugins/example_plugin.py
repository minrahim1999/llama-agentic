"""Example plugin — demonstrates how to add custom tools.

Drop this file (or any .py file) into the plugins/ directory.
Functions decorated with @tool are automatically registered and
available to the agent without any other changes.

To disable a plugin without deleting it, rename it to _example_plugin.py
(prefix with underscore).
"""

from agent.tools import tool


@tool
def get_current_dir() -> str:
    """Return the absolute path of the current working directory."""
    import os
    return os.getcwd()


@tool
def count_words(text: str) -> str:
    """Count words, lines, and characters in a text string.

    Args:
        text: The text to analyse.
    """
    words = len(text.split())
    lines = text.count("\n") + 1
    chars = len(text)
    return f"Words: {words}, Lines: {lines}, Characters: {chars}"
