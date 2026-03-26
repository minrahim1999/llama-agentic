"""A2A (Agent-to-Agent) JSON-RPC client and dynamic tool registration."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any
from urllib.parse import urljoin

from agent import __version__
from agent.a2a_config import A2AAgentConfig

_CARD_PATHS = (
    ".well-known/agent-card.json",
    "agent-card.json",
    "v1/card",
)


def _safe_tool_name(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_").lower()
    return safe or "agent"


def _jsonrpc_error(error: Any) -> RuntimeError:
    if isinstance(error, dict):
        code = error.get("code", "?")
        message = error.get("message", "unknown error")
        return RuntimeError(f"A2A error {code}: {message}")
    return RuntimeError(f"A2A error: {error}")


def _part_to_text(part: dict) -> str:
    kind = part.get("kind") or part.get("type")
    if kind == "text":
        return part.get("text", "")
    if kind == "data":
        data = part.get("data", {})
        return json.dumps(data, indent=2, sort_keys=True)
    if kind == "file":
        file_info = part.get("file", {})
        name = file_info.get("name") or file_info.get("uri") or "attachment"
        return f"[file: {name}]"
    return ""


def _parts_to_text(parts: list[dict]) -> str:
    chunks = [_part_to_text(part) for part in parts if isinstance(part, dict)]
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _extract_message_text(message: dict) -> str:
    parts = message.get("parts", [])
    if isinstance(parts, list):
        text = _parts_to_text(parts)
        if text:
            return text
    return ""


def _extract_task_text(task: dict) -> str:
    text_chunks: list[str] = []

    status = task.get("status", {})
    if isinstance(status, dict):
        state = status.get("state")
        status_message = status.get("message")
        if isinstance(status_message, dict):
            status_text = _extract_message_text(status_message)
            if status_text:
                text_chunks.append(status_text)
        if state and not text_chunks:
            text_chunks.append(f"[task state: {state}]")

    for artifact in task.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        parts = artifact.get("parts", [])
        if isinstance(parts, list):
            artifact_text = _parts_to_text(parts)
            if artifact_text:
                text_chunks.append(artifact_text)

    if text_chunks:
        return "\n".join(text_chunks).strip()

    task_id = task.get("id") or task.get("taskId") or "unknown"
    state = status.get("state") if isinstance(status, dict) else None
    if state:
        return f"[A2A task {task_id}: {state}]"
    return f"[A2A task {task_id}]"


def _result_to_text(result: dict) -> str:
    kind = result.get("kind")
    if kind == "message":
        text = _extract_message_text(result)
        return text or "(empty message)"
    if kind == "task":
        return _extract_task_text(result)
    if kind == "status-update":
        status = result.get("status", {})
        state = status.get("state") if isinstance(status, dict) else "updated"
        return f"[A2A task update: {state}]"
    if kind == "artifact-update":
        artifact = result.get("artifact", {})
        if isinstance(artifact, dict):
            parts = artifact.get("parts", [])
            if isinstance(parts, list):
                text = _parts_to_text(parts)
                if text:
                    return text
        return "[A2A artifact update]"

    if "message" in result and isinstance(result["message"], dict):
        text = _extract_message_text(result["message"])
        return text or "(empty message)"
    if "task" in result and isinstance(result["task"], dict):
        return _extract_task_text(result["task"])

    return json.dumps(result, indent=2, sort_keys=True)


class A2AClient:
    """A minimal JSON-RPC client for A2A agents over HTTP."""

    def __init__(self, config: A2AAgentConfig):
        self.config = config
        self.name = config.name
        self._client = None
        self._card: dict[str, Any] | None = None
        self._rpc_url: str | None = None
        self._id = 0

    @property
    def card(self) -> dict[str, Any] | None:
        return self._card

    @property
    def rpc_url(self) -> str | None:
        return self._rpc_url

    def start(self) -> None:
        import httpx

        self._client = httpx.Client(follow_redirects=True, timeout=30.0)
        self._card = self._fetch_agent_card()
        self._rpc_url = self._resolve_rpc_url()

    def stop(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _card_candidates(self) -> list[str]:
        raw = self.config.url.rstrip("/")
        if raw.endswith(".json"):
            return [raw]
        return [urljoin(f"{raw}/", path) for path in _CARD_PATHS]

    def _fetch_agent_card(self) -> dict[str, Any] | None:
        assert self._client is not None

        last_error: Exception | None = None
        for url in self._card_candidates():
            try:
                response = self._client.get(url, headers={"Accept": "application/json"}, timeout=10.0)
                response.raise_for_status()
                card = response.json()
                if isinstance(card, dict):
                    return card
            except Exception as exc:
                last_error = exc

        if self.config.url.rstrip("/").endswith(".json") and last_error is not None:
            raise RuntimeError(f"Failed to fetch Agent Card for '{self.name}': {last_error}")
        return None

    def _resolve_rpc_url(self) -> str:
        if self._card:
            primary = self._card.get("url")
            if isinstance(primary, str) and primary:
                return primary

            interfaces = self._card.get("additionalInterfaces", [])
            if isinstance(interfaces, list):
                for interface in interfaces:
                    if not isinstance(interface, dict):
                        continue
                    transport = str(interface.get("transport", "")).upper()
                    if transport == "JSONRPC":
                        url = interface.get("url")
                        if isinstance(url, str) and url:
                            return url

        if self.config.url.rstrip("/").endswith(".json"):
            raise RuntimeError(f"Agent Card for '{self.name}' does not declare an RPC URL")
        return self.config.url.rstrip("/")

    def list_skills(self) -> list[dict]:
        if not self._card:
            return []
        skills = self._card.get("skills", [])
        return skills if isinstance(skills, list) else []

    def send_message(
        self,
        message: str,
        task_id: str = "",
        context_id: str = "",
    ) -> str:
        assert self._client is not None
        assert self._rpc_url is not None

        msg: dict[str, Any] = {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": message}],
        }
        if task_id:
            msg["taskId"] = task_id
        if context_id:
            msg["contextId"] = context_id

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "message/send",
            "params": {
                "message": msg,
                "configuration": {
                    "acceptedOutputModes": ["text/plain"],
                    "blocking": True,
                },
                "metadata": {
                    "client": {
                        "name": "llama-agentic",
                        "version": __version__,
                    },
                },
            },
        }

        response = self._client.post(
            self._rpc_url,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("A2A server returned a non-object JSON-RPC payload")
        if "error" in body:
            raise _jsonrpc_error(body["error"])
        if body.get("id") != payload["id"]:
            raise RuntimeError(
                f"A2A response ID mismatch: expected {payload['id']}, got {body.get('id')}"
            )
        result = body.get("result")
        if not isinstance(result, dict):
            return "(empty response)"
        return _result_to_text(result)


def _a2a_schema(client: A2AClient) -> dict:
    description = client.config.description.strip()
    if not description and client.card:
        description = str(client.card.get("description", "")).strip()

    skill_names = [
        str(skill.get("name") or skill.get("id"))
        for skill in client.list_skills()
        if isinstance(skill, dict) and (skill.get("name") or skill.get("id"))
    ]
    if skill_names:
        skill_preview = ", ".join(skill_names[:4])
        if len(skill_names) > 4:
            skill_preview += ", …"
        description = f"{description} Skills: {skill_preview}".strip()

    if not description:
        description = "Send a message to a remote A2A agent."

    return {
        "type": "function",
        "function": {
            "name": f"a2a_{_safe_tool_name(client.name)}",
            "description": f"[A2A:{client.name}] {description}",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to send to the remote A2A agent.",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "Optional task ID to continue an existing A2A task.",
                    },
                    "context_id": {
                        "type": "string",
                        "description": "Optional context ID to continue an existing A2A conversation.",
                    },
                },
                "required": ["message"],
            },
        },
    }


def register_a2a_agent(client: A2AClient) -> str:
    """Register one remote A2A agent as a callable tool."""
    from agent import tools as registry

    tool_name = f"a2a_{_safe_tool_name(client.name)}"

    def tool_fn(message: str, task_id: str = "", context_id: str = "") -> str:
        return client.send_message(message=message, task_id=task_id, context_id=context_id)

    tool_fn.__name__ = tool_name
    registry._REGISTRY[tool_name] = {
        "fn": tool_fn,
        "schema": _a2a_schema(client),
    }
    return tool_name


class A2AManager:
    """Manages configured A2A agent clients for the current session."""

    def __init__(self):
        self._clients: dict[str, A2AClient] = {}
        self._tool_map: dict[str, str] = {}

    def load_and_connect(self, verbose: bool = False) -> dict[str, str]:
        from agent.a2a_config import load_a2a_config

        results: dict[str, str] = {}
        for name, agent_config in load_a2a_config().items():
            if not agent_config.enabled:
                continue
            try:
                client = A2AClient(agent_config)
                client.start()
                tool_name = register_a2a_agent(client)
                self._clients[name] = client
                self._tool_map[name] = tool_name
                results[name] = tool_name
                if verbose:
                    print(f"  A2A: {name} ({tool_name})")
            except Exception as exc:
                if verbose:
                    print(f"  A2A: {name} failed — {exc}")
        return results

    def stop_all(self) -> None:
        for client in self._clients.values():
            try:
                client.stop()
            except Exception:
                pass
        self._clients.clear()
        self._tool_map.clear()

    @property
    def connected_agents(self) -> dict[str, str]:
        return dict(self._tool_map)


_manager: A2AManager | None = None


def get_manager() -> A2AManager:
    global _manager
    if _manager is None:
        _manager = A2AManager()
    return _manager
