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
from urllib.parse import urljoin
from typing import Any

from agent import __version__
from agent.mcp_config import MCPServerConfig

_MCP_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "llama-agentic", "version": __version__}


class _LegacyHttpFallback(RuntimeError):
    """Signal that a server likely expects the deprecated HTTP+SSE transport."""


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
        tools: list[dict] = []
        cursor: str | None = None

        while True:
            params = {"cursor": cursor} if cursor else None
            result = self._request("tools/list", params=params, timeout=10.0)
            if not result:
                break
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break

        return tools

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
    """MCP client connecting to a remote MCP server over HTTP."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.name = config.name
        self._base = config.url.rstrip("/")
        self._client = None
        self._session_id: str | None = None
        self._negotiated_protocol_version = _MCP_PROTOCOL_VERSION
        self._initialized = False
        self._legacy_post_url: str | None = None
        self._legacy_stream_cm = None
        self._legacy_stream = None
        self._legacy_lines = None

    def start(self):
        import httpx

        self._client = httpx.Client(follow_redirects=True, timeout=30.0)
        try:
            self._initialize_streamable()
        except _LegacyHttpFallback:
            self._initialize_legacy_http_sse()

    def stop(self):
        if self._client is None:
            return

        try:
            if self._session_id:
                self._client.delete(self._base, headers=self._headers())
        except Exception:
            pass

        if self._legacy_stream is not None:
            try:
                self._legacy_stream.close()
            except Exception:
                pass
        if self._legacy_stream_cm is not None:
            try:
                self._legacy_stream_cm.__exit__(None, None, None)
            except Exception:
                pass

        self._client.close()
        self._client = None
        self._legacy_stream_cm = None
        self._legacy_stream = None
        self._legacy_lines = None
        self._legacy_post_url = None
        self._session_id = None
        self._initialized = False

    def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        cursor: str | None = None

        while True:
            params = {"cursor": cursor} if cursor else None
            result = self._request("tools/list", params=params, timeout=30.0)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break

        return tools

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._request("tools/call", {
            "name": name,
            "arguments": arguments,
        }, timeout=60.0)
        if not result:
            return "(no result)"

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

    def _initialize_streamable(self):
        result = self._request("initialize", {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": _CLIENT_INFO,
        }, timeout=30.0, allow_legacy_fallback=True)
        version = result.get("protocolVersion")
        if isinstance(version, str) and version:
            self._negotiated_protocol_version = version
        self._initialized = True
        self._notify("notifications/initialized")

    def _initialize_legacy_http_sse(self):
        assert self._client is not None
        stream_cm = self._client.stream(
            "GET",
            self._base,
            headers={"Accept": "text/event-stream"},
        )
        response = stream_cm.__enter__()
        response.raise_for_status()
        self._legacy_stream_cm = stream_cm
        self._legacy_stream = response
        self._legacy_lines = response.iter_lines()
        endpoint = self._read_legacy_endpoint()
        self._legacy_post_url = urljoin(f"{self._base}/", endpoint)

        result = self._request("initialize", {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": _CLIENT_INFO,
        }, timeout=30.0)
        version = result.get("protocolVersion")
        if isinstance(version, str) and version:
            self._negotiated_protocol_version = version
        self._initialized = True
        self._notify("notifications/initialized")

    def _request(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = 30.0,
        allow_legacy_fallback: bool = False,
    ) -> Any:
        req_id = self._next_request_id()
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params

        if self._legacy_post_url:
            return self._legacy_request(msg, req_id, timeout=timeout)
        return self._streamable_request(
            msg,
            req_id,
            timeout=timeout,
            allow_legacy_fallback=allow_legacy_fallback,
            allow_reinitialize=method != "initialize",
        )

    def _notify(self, method: str, params: dict | None = None):
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params

        if self._legacy_post_url:
            self._legacy_notify(msg)
            return

        assert self._client is not None
        response = self._client.post(
            self._base,
            json=msg,
            headers=self._headers(include_accept=False),
        )
        response.raise_for_status()

    def _streamable_request(
        self,
        payload: dict[str, Any],
        req_id: int,
        timeout: float,
        allow_legacy_fallback: bool,
        allow_reinitialize: bool,
    ) -> Any:
        assert self._client is not None

        with self._client.stream(
            "POST",
            self._base,
            json=payload,
            headers=self._headers(),
            timeout=timeout,
        ) as response:
            if allow_legacy_fallback and response.status_code in {400, 404, 405}:
                raise _LegacyHttpFallback()

            if response.status_code == 404 and self._session_id and allow_reinitialize:
                self._session_id = None
                self._initialize_streamable()
                return self._streamable_request(
                    payload,
                    req_id,
                    timeout=timeout,
                    allow_legacy_fallback=False,
                    allow_reinitialize=False,
                )

            response.raise_for_status()
            self._capture_session(response)
            return self._extract_response_message(response, req_id).get("result")

    def _legacy_request(self, payload: dict[str, Any], req_id: int, timeout: float) -> Any:
        assert self._client is not None
        assert self._legacy_post_url is not None

        response = self._client.post(
            self._legacy_post_url,
            json=payload,
            headers={"Accept": "application/json, text/event-stream"},
            timeout=timeout,
        )
        response.raise_for_status()

        if response.content:
            return self._extract_jsonrpc_message(response.json(), req_id).get("result")

        message = self._read_legacy_message(req_id)
        return message.get("result")

    def _legacy_notify(self, payload: dict[str, Any]):
        assert self._client is not None
        assert self._legacy_post_url is not None
        response = self._client.post(self._legacy_post_url, json=payload, timeout=10.0)
        response.raise_for_status()

    def _headers(self, include_accept: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {}
        if include_accept:
            headers["Accept"] = "application/json, text/event-stream"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self._initialized:
            headers["MCP-Protocol-Version"] = self._negotiated_protocol_version
        return headers

    def _capture_session(self, response):
        session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("MCP-Session-Id")
        if session_id:
            self._session_id = session_id

    def _extract_response_message(self, response, req_id: int) -> dict:
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" in content_type:
            return self._read_sse_message(response.iter_lines(), req_id)

        body = response.read()
        if not body:
            raise RuntimeError("MCP HTTP response body was empty")
        return self._extract_jsonrpc_message(json.loads(body), req_id)

    def _read_legacy_endpoint(self) -> str:
        event = self._next_sse_event(self._legacy_lines)
        if event["event"] != "endpoint":
            raise RuntimeError("Legacy MCP server did not send an endpoint event")
        endpoint = event["data"].strip()
        if not endpoint:
            raise RuntimeError("Legacy MCP server returned an empty endpoint")
        return endpoint

    def _read_legacy_message(self, req_id: int) -> dict:
        return self._read_sse_message(self._legacy_lines, req_id)

    def _read_sse_message(self, lines, req_id: int) -> dict:
        while True:
            event = self._next_sse_event(lines)
            data = event["data"].strip()
            if not data:
                continue
            message = self._extract_jsonrpc_message(json.loads(data), req_id, allow_unmatched=True)
            if message is None:
                continue
            return message

    def _next_sse_event(self, lines) -> dict[str, str]:
        if lines is None:
            raise RuntimeError("SSE stream is not open")

        event_name = "message"
        data_lines: list[str] = []

        for raw_line in lines:
            line = raw_line.decode() if isinstance(raw_line, bytes) else raw_line
            line = line.rstrip("\r")
            if not line:
                if data_lines:
                    return {"event": event_name, "data": "\n".join(data_lines)}
                event_name = "message"
                data_lines = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip() or "message"
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())

        if data_lines:
            return {"event": event_name, "data": "\n".join(data_lines)}
        raise RuntimeError("SSE stream ended before the MCP response arrived")

    def _extract_jsonrpc_message(
        self,
        payload: Any,
        req_id: int,
        allow_unmatched: bool = False,
    ) -> dict | None:
        if isinstance(payload, list):
            for item in payload:
                matched = self._extract_jsonrpc_message(item, req_id, allow_unmatched=allow_unmatched)
                if matched is not None:
                    return matched
            if allow_unmatched:
                return None
            raise RuntimeError(f"MCP response for request {req_id} was not found in the payload")

        if not isinstance(payload, dict):
            raise RuntimeError("MCP server returned a non-object JSON-RPC payload")

        if payload.get("id") != req_id:
            if allow_unmatched:
                return None
            raise RuntimeError(f"MCP response ID mismatch: expected {req_id}, got {payload.get('id')}")

        if "error" in payload:
            raise RuntimeError(f"MCP error: {payload['error']}")
        return payload

    def _next_request_id(self) -> int:
        if not hasattr(self, "_id"):
            self._id = 0
        self._id += 1
        return self._id


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
