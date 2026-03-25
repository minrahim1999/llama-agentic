"""Session persistence — save and load conversation history as JSON."""

import json
from datetime import datetime
from pathlib import Path
from agent.config import config


def _sessions_dir() -> Path:
    p = Path(config.sessions_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(history: list, name: str | None = None) -> str:
    """Serialize conversation history to a timestamped JSON file.

    Returns the path of the saved file.
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{name}_{ts}.json" if name else f"session_{ts}.json"
    path = _sessions_dir() / filename
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load(name: str) -> list:
    """Load a session by filename (with or without .json suffix).

    Raises FileNotFoundError if not found.
    """
    p = _sessions_dir()
    # Accept bare name or full filename
    candidates = [
        p / name,
        p / f"{name}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Session not found: {name}")


def list_sessions() -> list[str]:
    """Return all saved session filenames, newest first."""
    p = _sessions_dir()
    files = sorted(p.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [f.name for f in files]
