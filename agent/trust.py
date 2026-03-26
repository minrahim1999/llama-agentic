"""Trust store for tool confirmation decisions.

Trusted entries are stored as JSON:
  - project scope: .llama-agentic/trust.json   (checked in per-project dir)
  - global  scope: ~/.config/llama-agentic/trust.json

Key conventions
---------------
  "tool:<name>"      — a specific tool is always allowed
  "cmd:<word>"       — run_shell commands starting with <word> are always allowed
  "agent:all"        — blanket trust: ALL tools are allowed without prompting
  "agent:asked"      — the one-time "grant full access?" question has been shown
"""

from __future__ import annotations

import json
from pathlib import Path

_PROJECT_TRUST = Path(".llama-agentic/trust.json")

AGENT_ALL_KEY   = "agent:all"    # blanket trust granted
AGENT_ASKED_KEY = "agent:asked"  # one-time dialog already shown


def _global_trust_path() -> Path:
    return Path.home() / ".config" / "llama-agentic" / "trust.json"


def _load(path: Path) -> dict[str, bool]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(path: Path, store: dict[str, bool]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _key(tool_name: str, args: dict) -> str:
    """Return the trust key for a tool call."""
    if tool_name == "run_shell":
        cmd = args.get("command", "").strip().split()[0] if args.get("command") else ""
        return f"cmd:{cmd}" if cmd else f"tool:{tool_name}"
    return f"tool:{tool_name}"


def is_trusted(tool_name: str, args: dict) -> bool:
    """Return True if this tool call is pre-approved (no prompt needed)."""
    for store in (_load(_PROJECT_TRUST), _load(_global_trust_path())):
        if AGENT_ALL_KEY in store:
            return True
        key = _key(tool_name, args)
        if key in store or f"tool:{tool_name}" in store:
            return True
    return False


def full_access_asked() -> bool:
    """Return True if the one-time 'grant full access?' dialog has been shown."""
    for store in (_load(_PROJECT_TRUST), _load(_global_trust_path())):
        if AGENT_ASKED_KEY in store:
            return True
    return False


def mark_asked() -> None:
    """Record that the one-time dialog was shown (prevents re-asking on next run)."""
    store = _load(_PROJECT_TRUST)
    store[AGENT_ASKED_KEY] = True
    _save(_PROJECT_TRUST, store)


def remember(tool_name: str, args: dict, scope: str) -> None:
    """Persist a trust decision for a specific tool/command.

    Args:
        tool_name: Name of the tool being trusted.
        args:      Tool arguments (used to derive the key).
        scope:     "project" or "global".
    """
    key = _key(tool_name, args)
    path = _PROJECT_TRUST if scope == "project" else _global_trust_path()
    store = _load(path)
    store[key] = True
    _save(path, store)


def remember_all(scope: str) -> None:
    """Grant blanket trust for all tools.

    Args:
        scope: "project" or "global".
    """
    path = _PROJECT_TRUST if scope == "project" else _global_trust_path()
    store = _load(path)
    store[AGENT_ALL_KEY] = True
    store[AGENT_ASKED_KEY] = True
    _save(path, store)


def list_trusted(scope: str) -> dict[str, bool]:
    """Return all trust entries for the given scope."""
    path = _PROJECT_TRUST if scope == "project" else _global_trust_path()
    return _load(path)


def revoke(key: str, scope: str) -> bool:
    """Remove a trust entry. Returns True if it existed."""
    path = _PROJECT_TRUST if scope == "project" else _global_trust_path()
    store = _load(path)
    if key in store:
        del store[key]
        _save(path, store)
        return True
    return False
