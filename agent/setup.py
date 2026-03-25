"""First-run setup wizard — creates ~/.config/llama-agentic/config.env."""

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from agent.config import GLOBAL_CONFIG_DIR, GLOBAL_CONFIG_FILE

console = Console()

_DEFAULT_SERVER = "http://localhost:8080/v1"

# Preset model choices shown to the user
_MODEL_PRESETS = [
    ("1", "Qwen2.5-Coder-7B  (recommended, code tasks)"),
    ("2", "Qwen2.5-7B         (general agent)"),
    ("3", "Llama-3.1-8B       (general agent)"),
    ("4", "Mistral-7B-v0.3    (fast, lightweight)"),
    ("5", "Other              (enter manually)"),
]


def run_setup() -> bool:
    """Interactive setup wizard.  Returns True if setup completed successfully."""
    console.print(Panel(
        "[bold green]llama-agentic — first-run setup[/bold green]\n\n"
        "This wizard creates your global config at:\n"
        f"[dim]{GLOBAL_CONFIG_FILE}[/dim]",
        border_style="green",
    ))

    # ── Server URL ────────────────────────────────────────────────────────────
    server_url = Prompt.ask(
        "\n[bold]llama-server URL[/bold]",
        default=_DEFAULT_SERVER,
    )

    # ── Test connection ───────────────────────────────────────────────────────
    model_id = _detect_model(server_url)
    if model_id:
        console.print(f"[green]✓ Server reachable. Detected model: {model_id}[/green]")
    else:
        console.print(
            "[yellow]⚠ Could not reach the server. "
            "Make sure llama-server is running before starting the agent.[/yellow]"
        )
        if not Confirm.ask("Continue setup anyway?", default=True):
            return False

    # ── Model name ────────────────────────────────────────────────────────────
    console.print("\n[bold]Model name[/bold] (must match what llama-server reports):")
    if model_id:
        model_name = Prompt.ask("  Model", default=model_id)
    else:
        for num, label in _MODEL_PRESETS:
            console.print(f"  {num}. {label}")
        choice = Prompt.ask("  Choose", default="1")
        model_name = _resolve_model_choice(choice, model_id)

    # ── Context size ──────────────────────────────────────────────────────────
    ctx = Prompt.ask("\n[bold]Context window size (tokens)[/bold]", default="8192")

    # ── GPU layers ────────────────────────────────────────────────────────────
    gpu = Prompt.ask(
        "\n[bold]GPU layers[/bold] (-1 = full GPU, 0 = CPU only)",
        default="-1",
    )

    # ── Safety ───────────────────────────────────────────────────────────────
    unsafe = Confirm.ask(
        "\n[bold]Skip confirmation prompts[/bold] for shell/file writes?",
        default=False,
    )

    # ── Write config ──────────────────────────────────────────────────────────
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GLOBAL_CONFIG_FILE.write_text(
        f"LLAMA_SERVER_URL={server_url}\n"
        f"LLAMA_MODEL={model_name}\n"
        f"LLAMA_CTX_SIZE={ctx}\n"
        f"LLAMA_N_GPU_LAYERS={gpu}\n"
        f"UNSAFE_MODE={'true' if unsafe else 'false'}\n"
        f"MAX_TOOL_ITERATIONS=20\n"
        f"HISTORY_WINDOW=20\n",
        encoding="utf-8",
    )

    console.print(f"\n[green]✓ Config saved to {GLOBAL_CONFIG_FILE}[/green]")
    console.print("[dim]Edit that file anytime to change global defaults.[/dim]\n")

    # Reload config with new values
    from agent import config as cfg_module
    cfg_module.config.llama_server_url = server_url
    cfg_module.config.llama_model = model_name

    return True


def _detect_model(server_url: str) -> str | None:
    """Try to connect to llama-server and return the first model ID."""
    try:
        from openai import OpenAI
        client = OpenAI(base_url=server_url, api_key="not-required")
        models = client.models.list(timeout=3)
        if models.data:
            return models.data[0].id
    except Exception:
        pass
    return None


def _resolve_model_choice(choice: str, detected: str | None) -> str:
    presets = {
        "1": "qwen2.5-coder-7b-instruct",
        "2": "qwen2.5-7b-instruct",
        "3": "llama-3.1-8b-instruct",
        "4": "mistral-7b-instruct-v0.3",
    }
    if choice in presets:
        return presets[choice]
    # "5" or anything else → ask manually
    return Prompt.ask("  Enter model name", default=detected or "local-model")
