"""Tests for A2A config loading and JSON-RPC transport behavior."""

from __future__ import annotations

import json


class FakeResponse:
    def __init__(self, status_code=200, body=b""):
        self.status_code = status_code
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return json.loads(self._body.decode("utf-8"))


class FakeHttpClient:
    def __init__(self, get_responses=None, post_responses=None):
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []
        self.closed = False

    def get(self, url, headers=None, timeout=None):
        self.get_calls.append({
            "url": url,
            "headers": headers or {},
            "timeout": timeout,
        })
        return self.get_responses.pop(0)

    def post(self, url, json=None, headers=None, timeout=None):
        self.post_calls.append({
            "url": url,
            "json": json,
            "headers": headers or {},
            "timeout": timeout,
        })
        return self.post_responses.pop(0)

    def close(self):
        self.closed = True


def test_load_a2a_config_merges_global_and_local_with_local_override(tmp_path, monkeypatch):
    from agent import a2a_config as cfg

    global_file = tmp_path / "global-a2a.json"
    local_root = tmp_path / "project"
    local_root.mkdir()
    local_file = local_root / ".llama-agentic" / "a2a.json"
    local_file.parent.mkdir(parents=True)

    global_file.write_text(json.dumps({
        "agents": {
            "planner": {"url": "https://global.example/a2a", "description": "global"},
            "writer": {"url": "https://writer.example/a2a"},
        }
    }), encoding="utf-8")
    local_file.write_text(json.dumps({
        "agents": {
            "planner": {"url": "https://local.example/a2a", "description": "local"},
        }
    }), encoding="utf-8")

    monkeypatch.setattr(cfg, "GLOBAL_A2A_FILE", global_file)
    monkeypatch.setattr(cfg, "LOCAL_A2A_FILE", local_file)

    agents = cfg.load_a2a_config()

    assert agents["planner"].url == "https://local.example/a2a"
    assert agents["planner"].description == "local"
    assert agents["writer"].url == "https://writer.example/a2a"


def test_add_agent_only_updates_requested_scope(tmp_path, monkeypatch):
    from agent import a2a_config as cfg

    global_file = tmp_path / "global-a2a.json"
    local_file = tmp_path / "project" / ".llama-agentic" / "a2a.json"
    local_file.parent.mkdir(parents=True)

    global_file.write_text(json.dumps({
        "agents": {
            "global-agent": {"url": "https://global.example/a2a"},
        }
    }), encoding="utf-8")

    monkeypatch.setattr(cfg, "GLOBAL_A2A_FILE", global_file)
    monkeypatch.setattr(cfg, "LOCAL_A2A_FILE", local_file)

    cfg.add_agent(
        "local-agent",
        cfg.A2AAgentConfig(name="local-agent", url="https://local.example/a2a"),
        global_=False,
    )

    saved_local = json.loads(local_file.read_text(encoding="utf-8"))
    saved_global = json.loads(global_file.read_text(encoding="utf-8"))
    assert "local-agent" in saved_local["agents"]
    assert "global-agent" not in saved_local["agents"]
    assert "global-agent" in saved_global["agents"]


def test_a2a_client_fetches_agent_card_and_uses_declared_rpc_url(monkeypatch):
    import httpx
    from agent.a2a_client import A2AClient
    from agent.a2a_config import A2AAgentConfig

    fake_client = FakeHttpClient(
        get_responses=[
            FakeResponse(body=json.dumps({
                "name": "Planner",
                "description": "Plans work",
                "url": "https://rpc.example.test/a2a",
                "skills": [
                    {"id": "plan", "name": "Planning", "description": "Create plans"},
                ],
            })),
        ],
        post_responses=[
            FakeResponse(body=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "kind": "message",
                    "parts": [{"kind": "text", "text": "planned"}],
                },
            })),
        ],
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    client = A2AClient(A2AAgentConfig(name="planner", url="https://agent.example.test"))
    client.start()
    output = client.send_message("make a plan")
    client.stop()

    assert output == "planned"
    assert fake_client.get_calls[0]["url"] == "https://agent.example.test/.well-known/agent-card.json"
    assert fake_client.post_calls[0]["url"] == "https://rpc.example.test/a2a"
    payload = fake_client.post_calls[0]["json"]
    assert payload["method"] == "message/send"
    assert payload["params"]["message"]["parts"][0]["text"] == "make a plan"


def test_register_a2a_agent_exposes_remote_agent_as_tool(monkeypatch):
    import httpx

    from agent.a2a_client import A2AClient, register_a2a_agent
    from agent.a2a_config import A2AAgentConfig
    from agent.tools import _REGISTRY, dispatch

    fake_client = FakeHttpClient(
        get_responses=[
            FakeResponse(body=json.dumps({
                "name": "Research Agent",
                "description": "Find facts",
                "url": "https://rpc.example.test/a2a",
            })),
        ],
        post_responses=[
            FakeResponse(body=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "kind": "task",
                    "status": {
                        "state": "completed",
                        "message": {
                            "role": "agent",
                            "parts": [{"kind": "text", "text": "research result"}],
                        },
                    },
                },
            })),
        ],
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    client = A2AClient(A2AAgentConfig(name="research-agent", url="https://agent.example.test"))
    client.start()
    tool_name = register_a2a_agent(client)
    try:
        output = dispatch(tool_name, {"message": "find sources"})
        assert output == "research result"
        assert tool_name in _REGISTRY
    finally:
        _REGISTRY.pop(tool_name, None)
        client.stop()
