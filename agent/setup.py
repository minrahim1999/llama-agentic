"""First-run setup wizard — creates ~/.config/llama-agentic/config.env."""

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from agent.config import GLOBAL_CONFIG_DIR, GLOBAL_CONFIG_FILE

console = Console()

_DEFAULT_SERVER = "http://localhost:11435/v1"

# Preset model choices shown to the user
_MODEL_PRESETS = [
    ("1", "Qwen2.5-Coder-7B  (recommended, code tasks)"),
    ("2", "Qwen2.5-7B         (general agent)"),
    ("3", "Llama-3.1-8B       (general agent)"),
    ("4", "Mistral-7B-v0.3    (fast, lightweight)"),
    ("5", "Other              (enter manually)"),
]


def _os() -> str:
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


def _check_disk_space(min_gb: float = 5.0) -> tuple[float, bool]:
    try:
        stat = shutil.disk_usage(Path.home())
        free = stat.free / (1024 ** 3)
        return free, free >= min_gb
    except Exception:
        return 0.0, True


def _find_llama_server() -> str | None:
    found = shutil.which("llama-server")
    if found:
        return found
    for p in [
        "/opt/homebrew/bin/llama-server",
        "/usr/local/bin/llama-server",
        "/usr/bin/llama-server",
        r"C:\Program Files\llama.cpp\llama-server.exe",
    ]:
        if Path(p).exists():
            return p
    return None


def _install_llama_cpp() -> bool:
    os_name = _os()
    console.print("\n[yellow]llama-server not found. Trying auto-install…[/yellow]")
    if os_name == "macos" and shutil.which("brew"):
        result = subprocess.run(["brew", "install", "llama.cpp"], capture_output=False)
        return result.returncode == 0
    elif os_name == "linux":
        for pkg_mgr, cmd in [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "llama-cpp"]),
            ("snap",    ["sudo", "snap", "install", "llama-cpp"]),
        ]:
            if shutil.which(pkg_mgr):
                result = subprocess.run(cmd, capture_output=False)
                if result.returncode == 0:
                    return True
    elif os_name == "windows" and shutil.which("winget"):
        result = subprocess.run(
            ["winget", "install", "-e", "--id", "ggerganov.llama.cpp",
             "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=False,
        )
        return result.returncode == 0
    return False


def _offer_model_download() -> None:
    """After setup, offer to download a starter model if none exists."""
    from agent.model_manager import find_models, download, KNOWN_MODELS
    from agent.config import config

    existing = find_models(config.model_cache_dir)
    if existing:
        console.print(f"\n[dim]Found {len(existing)} model(s) already in cache — skipping download.[/dim]")
        return

    free_gb, _ = _check_disk_space(min_gb=3.0)
    if free_gb < 3.0:
        console.print(f"\n[yellow]Only {free_gb:.1f} GB free — skipping model download offer.[/yellow]")
        return

    console.print(f"\n[dim]Free space: {free_gb:.1f} GB[/dim]")
    if not Confirm.ask(
        "\n[bold]No models found. Download a starter model now?[/bold]",
        default=True,
    ):
        console.print("[dim]You can download later with: llama-agent download[/dim]")
        return

    # Show choices with sizes
    choices = [
        ("1", "qwen2.5-coder-7b",  "~4 GB — best for code tasks (recommended)"),
        ("2", "qwen2.5-coder-3b",  "~2 GB — lighter, good for limited RAM"),
        ("3", "llama3.2-3b",       "~2 GB — general agent, Meta"),
        ("4", "mistral-7b",        "~4 GB — fast general agent"),
    ]
    console.print("\n  Available models:")
    for num, alias, desc in choices:
        console.print(f"  {num}. [cyan]{alias}[/cyan]  [dim]{desc}[/dim]")

    choice = Prompt.ask("  Choose", choices=["1", "2", "3", "4"], default="1")
    alias = next(a for n, a, _ in choices if n == choice)

    console.print(f"\n[dim]Downloading {alias} from Hugging Face…[/dim]")
    try:
        path = download(alias_or_repo=alias)
        console.print(f"[green]✓ Model saved:[/green] {path}")
    except Exception as e:
        console.print(f"[red]Download failed:[/red] {e}")
        console.print("[dim]Try later: llama-agent download[/dim]")


def run_setup() -> bool:
    """Interactive setup wizard.  Returns True if setup completed successfully."""
    console.print(Panel(
        "[bold green]llama-agentic — first-run setup[/bold green]\n\n"
        "This wizard creates your global config at:\n"
        f"[dim]{GLOBAL_CONFIG_FILE}[/dim]",
        border_style="green",
    ))

    # ── Disk space ────────────────────────────────────────────────────────────
    free_gb, space_ok = _check_disk_space(min_gb=5.0)
    if space_ok:
        console.print(f"[dim]✓ Free disk space: {free_gb:.1f} GB[/dim]")
    else:
        console.print(
            f"[yellow]⚠ Low disk space: {free_gb:.1f} GB free.\n"
            "  LLM models typically need 2–8 GB. You may run out of space.[/yellow]"
        )
        if not Confirm.ask("Continue anyway?", default=True):
            return False

    # ── llama-server detection / install ─────────────────────────────────────
    llama_bin = _find_llama_server()
    if llama_bin:
        console.print(f"[dim]✓ llama-server: {llama_bin}[/dim]")
    else:
        console.print("[yellow]⚠ llama-server not found in PATH.[/yellow]")
        if Confirm.ask("  Attempt auto-install now?", default=True):
            installed = _install_llama_cpp()
            if installed:
                llama_bin = _find_llama_server()
                if llama_bin:
                    console.print(f"[green]✓ llama-server installed: {llama_bin}[/green]")
                else:
                    console.print("[yellow]Installed but not in PATH yet — restart shell after setup.[/yellow]")
            else:
                console.print(
                    "[yellow]Auto-install failed.\n"
                    "  macOS:   brew install llama.cpp\n"
                    "  Linux:   see https://github.com/ggerganov/llama.cpp#build\n"
                    "  Windows: https://github.com/ggerganov/llama.cpp/releases[/yellow]"
                )
        if not Confirm.ask("Continue setup without llama-server?", default=True):
            return False

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

    # ── Model download ────────────────────────────────────────────────────────
    _offer_model_download()

    # ── Auto-start hint ───────────────────────────────────────────────────────
    console.print(
        "\n[dim]Tip: enable auto-start so llama-server launches at login:[/dim]\n"
        "  [bold]llama-agent autostart enable[/bold]\n"
    )

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
