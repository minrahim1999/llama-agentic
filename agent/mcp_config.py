"""MCP server configuration — load/save ~/.config/llama-agentic/mcp.json."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent.config import GLOBAL_CONFIG_DIR


GLOBAL_MCP_FILE = GLOBAL_CONFIG_DIR / "mcp.json"
LOCAL_MCP_FILE = Path(".llama-agentic") / "mcp.json"


@dataclass
class MCPServerConfig:
    name: str
    # Stdio transport
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # HTTP transport
    url: str = ""
    # Metadata
    description: str = ""
    enabled: bool = True

    @property
    def transport(self) -> str:
        return "http" if self.url else "stdio"

    def to_dict(self) -> dict:
        d: dict = {"enabled": self.enabled}
        if self.description:
            d["description"] = self.description
        if self.transport == "stdio":
            d["command"] = self.command
            if self.args:
                d["args"] = self.args
            if self.env:
                d["env"] = self.env
        else:
            d["url"] = self.url
        return d


def load_mcp_config() -> dict[str, MCPServerConfig]:
    """Load MCP servers from global + per-project config. Project overrides global."""
    servers: dict[str, MCPServerConfig] = {}

    for config_file in [GLOBAL_MCP_FILE, LOCAL_MCP_FILE]:
        if not Path(config_file).exists():
            continue
        try:
            data = json.loads(Path(config_file).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for name, spec in data.get("servers", {}).items():
            servers[name] = MCPServerConfig(
                name=name,
                command=spec.get("command", ""),
                args=spec.get("args", []),
                env=spec.get("env", {}),
                url=spec.get("url", ""),
                description=spec.get("description", ""),
                enabled=spec.get("enabled", True),
            )

    return servers


def save_mcp_config(servers: dict[str, MCPServerConfig], global_: bool = True):
    """Write servers to global or per-project mcp.json."""
    target = GLOBAL_MCP_FILE if global_ else LOCAL_MCP_FILE
    Path(target).parent.mkdir(parents=True, exist_ok=True)

    data: dict = {"servers": {}}
    for name, srv in servers.items():
        data["servers"][name] = srv.to_dict()

    Path(target).write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_server(name: str, spec: MCPServerConfig, global_: bool = True):
    """Add or update a server entry in the config."""
    servers = load_mcp_config()
    servers[name] = spec
    save_mcp_config(servers, global_=global_)


def remove_server(name: str, global_: bool = True) -> bool:
    """Remove a server entry. Returns True if it existed."""
    servers = load_mcp_config()
    if name not in servers:
        return False
    del servers[name]
    save_mcp_config(servers, global_=global_)
    return True
