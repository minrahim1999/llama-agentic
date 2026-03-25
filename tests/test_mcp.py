"""Tests for MCP HTTP transport behavior."""

import json


class FakeResponse:
    def __init__(self, status_code=200, headers=None, body=b"", lines=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")
        self._lines = lines or []
        self.closed = False

    @property
    def content(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def read(self):
        return self._body

    def json(self):
        return json.loads(self._body.decode("utf-8"))

    def iter_lines(self):
        for line in self._lines:
            yield line

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class FakeStreamContext:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, exc_type, exc, tb):
        self.response.close()
        return False


class FakeHttpClient:
    def __init__(self, stream_responses=None, post_responses=None):
        self.stream_responses = list(stream_responses or [])
        self.post_responses = list(post_responses or [])
        self.stream_calls = []
        self.post_calls = []
        self.delete_calls = []
        self.closed = False

    def stream(self, method, url, headers=None, json=None, timeout=None):
        self.stream_calls.append({
            "method": method,
            "url": url,
            "headers": headers or {},
            "json": json,
            "timeout": timeout,
        })
        response = self.stream_responses.pop(0)
        return FakeStreamContext(response)

    def post(self, url, json=None, headers=None, timeout=None):
        self.post_calls.append({
            "url": url,
            "json": json,
            "headers": headers or {},
            "timeout": timeout,
        })
        return self.post_responses.pop(0)

    def delete(self, url, headers=None):
        self.delete_calls.append({"url": url, "headers": headers or {}})
        return FakeResponse(status_code=204)

    def close(self):
        self.closed = True


def test_streamable_http_supports_sessions_and_pagination(monkeypatch):
    import httpx
    from agent.mcp_client import MCPHttpClient
    from agent.mcp_config import MCPServerConfig

    fake_client = FakeHttpClient(
        stream_responses=[
            FakeResponse(
                headers={
                    "content-type": "application/json",
                    "Mcp-Session-Id": "sess-123",
                },
                body=json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"protocolVersion": "2025-06-18"},
                }),
            ),
            FakeResponse(
                headers={"content-type": "application/json"},
                body=json.dumps({
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [{"name": "alpha"}],
                        "nextCursor": "page-2",
                    },
                }),
            ),
            FakeResponse(
                headers={"content-type": "application/json"},
                body=json.dumps({
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {"tools": [{"name": "beta"}]},
                }),
            ),
            FakeResponse(
                headers={"content-type": "application/json"},
                body=json.dumps({
                    "jsonrpc": "2.0",
                    "id": 4,
                    "result": {
                        "content": [{"type": "text", "text": "done"}],
                    },
                }),
            ),
        ],
        post_responses=[FakeResponse(status_code=202)],
    )

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    client = MCPHttpClient(MCPServerConfig(name="demo", url="https://mcp.example.test"))
    client.start()
    tools = client.list_tools()
    output = client.call_tool("demo_tool", {"value": 1})
    client.stop()

    assert [tool["name"] for tool in tools] == ["alpha", "beta"]
    assert output == "done"

    first_list_headers = fake_client.stream_calls[1]["headers"]
    assert first_list_headers["Mcp-Session-Id"] == "sess-123"
    assert first_list_headers["MCP-Protocol-Version"] == "2025-06-18"

    second_list_payload = fake_client.stream_calls[2]["json"]
    assert second_list_payload["params"]["cursor"] == "page-2"

    assert fake_client.delete_calls[0]["headers"]["Mcp-Session-Id"] == "sess-123"


def test_stdio_client_lists_all_tool_pages(monkeypatch):
    from agent.mcp_client import MCPStdioClient
    from agent.mcp_config import MCPServerConfig

    client = MCPStdioClient(MCPServerConfig(name="stdio", command="dummy"))
    responses = iter([
        {"tools": [{"name": "one"}], "nextCursor": "page-2"},
        {"tools": [{"name": "two"}]},
    ])

    monkeypatch.setattr(client, "_request", lambda method, params=None, timeout=10.0: next(responses))

    tools = client.list_tools()

    assert [tool["name"] for tool in tools] == ["one", "two"]


def test_streamable_http_parses_sse_post_responses(monkeypatch):
    import httpx
    from agent.mcp_client import MCPHttpClient
    from agent.mcp_config import MCPServerConfig

    fake_client = FakeHttpClient(
        stream_responses=[
            FakeResponse(
                headers={"content-type": "application/json"},
                body=json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"protocolVersion": "2025-06-18"},
                }),
            ),
            FakeResponse(
                headers={"content-type": "text/event-stream"},
                lines=[
                    'event: message',
                    'data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"streamed"}]}}',
                    "",
                ],
            ),
        ],
        post_responses=[FakeResponse(status_code=202)],
    )

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    client = MCPHttpClient(MCPServerConfig(name="demo", url="https://mcp.example.test"))
    client.start()
    output = client.call_tool("demo_tool", {})

    assert output == "streamed"


def test_http_client_falls_back_to_legacy_sse(monkeypatch):
    import httpx
    from agent.mcp_client import MCPHttpClient
    from agent.mcp_config import MCPServerConfig

    fake_client = FakeHttpClient(
        stream_responses=[
            FakeResponse(
                status_code=405,
                headers={"content-type": "application/json"},
                body="{}",
            ),
            FakeResponse(
                headers={"content-type": "text/event-stream"},
                lines=[
                    "event: endpoint",
                    "data: /messages",
                    "",
                    'event: message',
                    'data: {"jsonrpc":"2.0","id":2,"result":{"protocolVersion":"2024-11-05"}}',
                    "",
                    'event: message',
                    'data: {"jsonrpc":"2.0","id":3,"result":{"tools":[{"name":"legacy_tool"}]}}',
                    "",
                ],
            ),
        ],
        post_responses=[
            FakeResponse(status_code=202),
            FakeResponse(status_code=202),
            FakeResponse(status_code=202),
        ],
    )

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    client = MCPHttpClient(MCPServerConfig(name="legacy", url="https://mcp.example.test"))
    client.start()
    tools = client.list_tools()

    assert [tool["name"] for tool in tools] == ["legacy_tool"]
    assert fake_client.post_calls[0]["url"] == "https://mcp.example.test/messages"
    assert fake_client.post_calls[0]["json"]["method"] == "initialize"
