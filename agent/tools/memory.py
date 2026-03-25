"""Memory tools — let the agent persist and recall facts across sessions."""

from agent.tools import tool
from agent import memory as mem_store


@tool
def save_memory(key: str, content: str) -> str:
    """Save a piece of information to persistent memory so it is available in future sessions.

    Args:
        key: Short identifier for the memory (e.g. 'user_preferences', 'project_notes').
        content: The text content to store.
    """
    return mem_store.save(key, content)


@tool
def recall_memory(key: str) -> str:
    """Recall a previously saved memory entry by key.

    Args:
        key: The identifier used when the memory was saved.
    """
    value = mem_store.load(key)
    if value is None:
        return f"No memory found for key: '{key}'"
    return value


@tool
def list_memories() -> str:
    """List all saved memory keys."""
    keys = mem_store.list_memories()
    if not keys:
        return "No memories saved yet."
    return "Saved memories:\n" + "\n".join(f"  - {k}" for k in keys)


@tool
def delete_memory(key: str) -> str:
    """Delete a memory entry by key.

    Args:
        key: The identifier of the memory to delete.
    """
    return mem_store.forget(key)
