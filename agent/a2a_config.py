"""A2A agent configuration — load/save ~/.config/llama-agentic/a2a.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agent.config import GLOBAL_CONFIG_DIR


GLOBAL_A2A_FILE = GLOBAL_CONFIG_DIR / "a2a.json"
LOCAL_A2A_FILE = Path(".llama-agentic") / "a2a.json"


@dataclass
class A2AAgentConfig:
    name: str
    url: str
    description: str = ""
    enabled: bool = True

    def to_dict(self) -> dict:
        data = {
            "url": self.url,
            "enabled": self.enabled,
        }
        if self.description:
            data["description"] = self.description
        return data


def _load_config_file(config_file: Path) -> dict[str, A2AAgentConfig]:
    if not config_file.exists():
        return {}

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    agents: dict[str, A2AAgentConfig] = {}
    for name, spec in data.get("agents", {}).items():
        url = spec.get("url", "")
        if not url:
            continue
        agents[name] = A2AAgentConfig(
            name=name,
            url=url,
            description=spec.get("description", ""),
            enabled=spec.get("enabled", True),
        )
    return agents


def load_a2a_config() -> dict[str, A2AAgentConfig]:
    """Load A2A agents from global + per-project config. Project overrides global."""
    agents: dict[str, A2AAgentConfig] = {}
    agents.update(_load_config_file(GLOBAL_A2A_FILE))
    agents.update(_load_config_file(LOCAL_A2A_FILE))
    return agents


def save_a2a_config(agents: dict[str, A2AAgentConfig], global_: bool = True) -> None:
    """Write agents to global or per-project a2a.json."""
    target = GLOBAL_A2A_FILE if global_ else LOCAL_A2A_FILE
    target.parent.mkdir(parents=True, exist_ok=True)

    data = {"agents": {name: agent.to_dict() for name, agent in agents.items()}}
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def add_agent(name: str, spec: A2AAgentConfig, global_: bool = True) -> None:
    target = GLOBAL_A2A_FILE if global_ else LOCAL_A2A_FILE
    agents = _load_config_file(target)
    agents[name] = spec
    save_a2a_config(agents, global_=global_)


def remove_agent(name: str, global_: bool = True) -> bool:
    target = GLOBAL_A2A_FILE if global_ else LOCAL_A2A_FILE
    agents = _load_config_file(target)
    if name not in agents:
        return False
    del agents[name]
    save_a2a_config(agents, global_=global_)
    return True
