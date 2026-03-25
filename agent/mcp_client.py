"""MCP (Model Context Protocol) client — stdio and HTTP transports.

Supports connecting to any MCP server, discovering its tools, and calling them.
Discovered tools are dynamically registered into the @tool registry so the agent
can use them exactly like built-in tools.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any

from agent.mcp_config import MCPServerConfig

_MCP_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "llama-agentic", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Stdio transport
# ---------------------------------------------------------------------------

class MCPStdioClient:
    """MCP client communicating over subprocess stdin/stdout (JSON-RPC)."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.name = config.name
        self._proc: subprocess.Popen | None = None
        self._id = 0
        self._lock = threading.Lock()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def start(self):
        env = {**os.environ, **self.config.env}
        self._proc = subprocess.Popen(
            [self.config.command, *self.config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
            bufsize=1,
        )
        self._initialize()

    def stop(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
        self._proc = None

    def _send(self, obj: dict) -> None:
        line = json.dumps(obj) + "\n"
        assert self._proc and self._proc.stdin
        with self._lock:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()

    def _recv(self, timeout: float = 10.0) -> dict:
        assert self._proc and self._proc.stdout
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self._proc.stdout.readline()
            if line:
                return json.loads(line.strip())
            if self._proc.poll() is not None:
                raise RuntimeError(f"MCP server '{self.name}' exited unexpectedly")
            time.sleep(0.05)
        raise TimeoutError(f"MCP server '{self.name}' did not respond in {timeout}s")

    def _request(self, method: str, params: dict | None = None, timeout: float = 10.0) -> Any:
        req_id = self._next_id()
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        # Drain until we get our response (skip notifications)
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = self._recv(timeout=max(1.0, deadline - time.time()))
            if resp.get("id") == req_id:
                if "error" in resp:
                    raise RuntimeError(f"MCP error: {resp['error']}")
                return resp.get("result")
        raise TimeoutError(f"No response for request {req_id}")

    def _notify(self, method: str, params: dict | None = None):
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def _initialize(self):
        result = self._request("initialize", {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "clientInfo": _CLIENT_INFO,
        }, timeout=15.0)
        self._notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict]:
        result = self._request("tools/list", timeout=10.0)
        return result.get("tools", []) if result else []

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._request("tools/call", {
            "name": name,
            "arguments": arguments,
        }, timeout=30.0)
        if not result:
            return "(no result)"
        # MCP tools/call returns {"content": [...], "isError": bool}
        content = result.get("content", [])
        parts = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif item.get("type") == "image":
                parts.append(f"[image: {item.get('mimeType', 'unknown')}]")
            elif item.get("type") == "resource":
                resource = item.get("resource", {})
                parts.append(resource.get("text", f"[resource: {resource.get('uri', '?')}]"))
        output = "\n".join(parts) or "(empty response)"
        if result.get("isError"):
            output = f"[MCP tool error]\n{output}"
        return output


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------

class MCPHttpClient:
    """MCP client connecting to an HTTP server."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.name = config.name
        self._base = config.url.rstrip("/")

    def start(self):
        pass  # No subprocess to launch

    def stop(self):
        pass

    def list_tools(self) -> list[dict]:
        try:
            import httpx
            resp = httpx.get(f"{self._base}/tools", timeout=10)
            resp.raise_for_status()
            return resp.json().get("tools", [])
        except Exception as e:
            raise RuntimeError(f"MCP HTTP list_tools failed: {e}")

    def call_tool(self, name: str, arguments: dict) -> str:
        try:
            import httpx
            resp = httpx.post(
                f"{self._base}/tools/call",
                json={"name": name, "arguments": arguments},
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            content = result.get("content", [])
            parts = [item.get("text", "") for item in content if item.get("type") == "text"]
            return "\n".join(parts) or "(empty response)"
        except Exception as e:
            raise RuntimeError(f"MCP HTTP call_tool failed: {e}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_client(config: MCPServerConfig) -> MCPStdioClient | MCPHttpClient:
    if config.transport == "http":
        return MCPHttpClient(config)
    return MCPStdioClient(config)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def _mcp_schema_to_tool_schema(server_name: str, tool: dict) -> dict:
    """Convert an MCP tool schema to OpenAI function-calling format."""
    input_schema = tool.get("inputSchema") or {"type": "object", "properties": {}, "required": []}
    return {
        "type": "function",
        "function": {
            "name": f"mcp_{server_name}__{tool['name']}",
            "description": f"[MCP:{server_name}] {tool.get('description', '')}",
            "parameters": input_schema,
        },
    }


def register_mcp_tools(client: MCPStdioClient | MCPHttpClient) -> list[str]:
    """Discover and register all tools from an MCP server. Returns tool names."""
    from agent import tools as registry

    tools = client.list_tools()
    registered = []

    for tool_spec in tools:
        original_name = tool_spec["name"]
        registered_name = f"mcp_{client.name}__{original_name}"

        # Create a closure capturing the client + original name
        def make_fn(c, n):
            def tool_fn(**kwargs) -> str:
                return c.call_tool(n, kwargs)
            tool_fn.__name__ = f"mcp_{c.name}__{n}"
            return tool_fn

        fn = make_fn(client, original_name)
        schema = _mcp_schema_to_tool_schema(client.name, tool_spec)
        registry._REGISTRY[registered_name] = {"fn": fn, "schema": schema}
        registered.append(registered_name)

    return registered


# ---------------------------------------------------------------------------
# Session-level MCP manager
# ---------------------------------------------------------------------------

class MCPManager:
    """Manages all MCP server connections for a session."""

    def __init__(self):
        self._clients: dict[str, MCPStdioClient | MCPHttpClient] = {}
        self._tool_map: dict[str, list[str]] = {}  # server_name → [tool_names]

    def load_and_connect(self, verbose: bool = False) -> dict[str, list[str]]:
        """Load config, connect to all enabled servers, register their tools."""
        from agent.mcp_config import load_mcp_config

        servers = load_mcp_config()
        results: dict[str, list[str]] = {}

        for name, srv_config in servers.items():
            if not srv_config.enabled:
                continue
            try:
                client = make_client(srv_config)
                client.start()
                tool_names = register_mcp_tools(client)
                self._clients[name] = client
                self._tool_map[name] = tool_names
                results[name] = tool_names
                if verbose:
                    print(f"  MCP: {name} ({len(tool_names)} tools)")
            except Exception as e:
                if verbose:
                    print(f"  MCP: {name} failed — {e}")

        return results

    def stop_all(self):
        for client in self._clients.values():
            try:
                client.stop()
            except Exception:
                pass
        self._clients.clear()
        self._tool_map.clear()

    @property
    def connected_servers(self) -> dict[str, list[str]]:
        return dict(self._tool_map)


# Global manager instance
_manager: MCPManager | None = None


def get_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager
