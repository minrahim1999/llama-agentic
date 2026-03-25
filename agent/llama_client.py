"""Thin wrapper around the openai SDK pointed at a local llama-server."""

from openai import OpenAI
from agent.config import config


def get_client() -> OpenAI:
    return OpenAI(base_url=config.llama_server_url, api_key="not-required")


def list_models() -> list[str]:
    client = get_client()
    models = client.models.list()
    return [m.id for m in models.data]


def check_server() -> tuple[bool, str]:
    """Check if llama-server is reachable. Returns (ok, message)."""
    try:
        client = get_client()
        models = client.models.list(timeout=3)
        model_id = models.data[0].id if models.data else "unknown"
        return True, model_id
    except Exception:
        return False, (
            f"Cannot reach llama-server at {config.llama_server_url}\n"
            f"Start it with: ./scripts/start_server.sh\n"
            f"Or run: llama-agent --setup to reconfigure"
        )
