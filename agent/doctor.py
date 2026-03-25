"""Environment diagnostics — `llama-agent doctor`."""

import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


def run_doctor() -> bool:
    """Run all checks and print a status table. Returns True if all pass."""
    from agent.config import config
    from agent.llama_client import check_server
    from agent.model_manager import find_models

    checks: list[tuple[str, bool, str]] = []

    # Python version
    major, minor = sys.version_info[:2]
    ok = major == 3 and minor >= 11
    checks.append(("Python ≥ 3.11", ok, f"{major}.{minor}"))

    # llama-server binary
    bin_path = shutil.which(config.llama_server_bin)
    ok = bin_path is not None
    checks.append(("llama-server binary", ok, bin_path or f"'{config.llama_server_bin}' not found in PATH"))

    # llama-server reachable
    server_ok, server_msg = check_server()
    checks.append(("llama-server running", server_ok, server_msg))

    # huggingface_hub
    try:
        import huggingface_hub  # noqa: F401
        hf_ok = True
        hf_msg = huggingface_hub.__version__
    except ImportError:
        hf_ok = False
        hf_msg = "not installed (pip install huggingface-hub)"
    checks.append(("huggingface-hub", hf_ok, hf_msg))

    # Model cache
    cache = Path(config.model_cache_dir)
    models = find_models()
    ok = len(models) > 0
    checks.append((
        "GGUF model(s) in cache",
        ok,
        f"{len(models)} model(s) in {cache}" if ok else f"none in {cache} — run: llama-agent download <model>",
    ))

    # Global config
    from agent.config import GLOBAL_CONFIG_FILE
    ok = GLOBAL_CONFIG_FILE.exists()
    checks.append(("Global config", ok, str(GLOBAL_CONFIG_FILE) if ok else f"missing — run: llama-agent --setup"))

    # Print table
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail", style="dim")

    all_pass = True
    for label, passed, detail in checks:
        status = "[green]✓ OK[/green]" if passed else "[red]✗ FAIL[/red]"
        if not passed:
            all_pass = False
        table.add_row(label, status, detail)

    console.print(table)

    if all_pass:
        console.print("\n[green]All checks passed.[/green]")
    else:
        console.print("\n[yellow]Some checks failed — fix the issues above and re-run.[/yellow]")

    return all_pass
