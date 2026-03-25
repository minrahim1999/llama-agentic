"""Persistent agent memory — simple markdown files in memory/ dir."""

from pathlib import Path
from agent.config import config


def _memory_dir() -> Path:
    p = Path(config.memory_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(key: str, content: str) -> str:
    """Write a named memory entry to disk."""
    path = _memory_dir() / f"{key}.md"
    path.write_text(content, encoding="utf-8")
    return f"Memory saved: {key}"


def load(key: str) -> str | None:
    """Read a named memory entry. Returns None if not found."""
    path = _memory_dir() / f"{key}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def load_all() -> str:
    """Return concatenated contents of all memory files for injection into prompt."""
    p = _memory_dir()
    files = sorted(p.glob("*.md"))
    if not files:
        return ""
    sections = []
    for f in files:
        sections.append(f"### {f.stem}\n{f.read_text(encoding='utf-8')}")
    return "\n\n".join(sections)


def list_memories() -> list[str]:
    return [f.stem for f in sorted(_memory_dir().glob("*.md"))]


def forget(key: str) -> str:
    path = _memory_dir() / f"{key}.md"
    if path.exists():
        path.unlink()
        return f"Memory deleted: {key}"
    return f"Memory not found: {key}"
