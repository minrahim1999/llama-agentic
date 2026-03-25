"""Auto-start / stop llama-server as a background subprocess.

Used when config.auto_start_server=True and the server is not already running.
"""

import atexit
import shutil
import signal
import subprocess
import time
from pathlib import Path

from agent.config import config, configured_model_path
from agent.llama_client import check_server

_proc: subprocess.Popen | None = None


def resolve_model_file(model_path: str | None = None) -> str | None:
    """Resolve the GGUF file to use for server startup.

    Preference order:
      1. explicit `model_path` argument
      2. configured `LLAMA_MODEL_PATH`
      3. first GGUF found in `model_cache_dir`
    """
    if model_path:
        candidate = Path(model_path).expanduser()
        return str(candidate.resolve()) if candidate.exists() else str(candidate)

    configured = configured_model_path()
    if configured is not None:
        return str(configured)

    return _find_model_file()


def _find_model_file() -> str | None:
    """Return first .gguf found in model_cache_dir, or None."""
    cache = Path(config.model_cache_dir)
    if not cache.exists():
        return None
    for f in sorted(cache.glob("**/*.gguf")):
        return str(f)
    return None


def start_server(model_path: str | None = None, wait_secs: int = 30) -> bool:
    """Launch llama-server in the background.

    Args:
        model_path: Path to GGUF model. Falls back to configured path, then cache scan.
        wait_secs: Seconds to wait for server to become healthy.

    Returns True if server is up, False otherwise.
    """
    global _proc

    # Check if already running
    ok, _ = check_server()
    if ok:
        return True

    # Resolve model
    model_path = resolve_model_file(model_path)
    if not model_path:
        return False

    # Resolve binary
    bin_path = shutil.which(config.llama_server_bin) or config.llama_server_bin
    if not shutil.which(bin_path):
        return False

    # Parse host/port from URL  (http://localhost:11435/v1 → 11435)
    port = 11435
    try:
        from urllib.parse import urlparse
        parsed = urlparse(config.llama_server_url)
        port = parsed.port or 11435
        host = parsed.hostname or "127.0.0.1"
    except Exception:
        host = "127.0.0.1"

    cmd = [
        bin_path,
        "--model", model_path,
        "--host", host,
        "--port", str(port),
        "--ctx-size", str(config.llama_ctx_size),
        "--n-gpu-layers", str(config.llama_n_gpu_layers),
        "--jinja",
    ]

    _proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Register cleanup
    atexit.register(_stop_on_exit)

    # Poll until healthy or timeout
    deadline = time.time() + wait_secs
    while time.time() < deadline:
        time.sleep(1)
        ok, _ = check_server()
        if ok:
            return True
        if _proc.poll() is not None:  # process died
            return False

    return False


def stop_server():
    """Terminate the managed llama-server process."""
    global _proc
    if _proc and _proc.poll() is None:
        _proc.send_signal(signal.SIGTERM)
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


def _stop_on_exit():
    if config.auto_stop_server:
        stop_server()


def ensure_server(model_path: str | None = None) -> tuple[bool, str]:
    """Ensure llama-server is running.

    If already running, returns (True, model_id).
    If auto_start_server=True, tries to start it.
    Returns (ok, message).
    """
    ok, msg = check_server()
    if ok:
        return True, msg

    if not config.auto_start_server:
        return False, msg

    # Try auto-start
    model = resolve_model_file(model_path)
    if not model:
        configured = config.llama_model_path.strip()
        configured_hint = f"Configured LLAMA_MODEL_PATH was not found: {configured}\n" if configured else ""
        return False, (
            f"{msg}\n"
            f"{configured_hint}"
            f"No GGUF model found in {config.model_cache_dir}.\n"
            f"Download one with: llama-agent download <model>"
        )

    print(f"Starting llama-server with {Path(model).name} …", flush=True)
    started = start_server(model_path=model)
    if started:
        _, model_id = check_server()
        return True, model_id

    return False, (
        "Failed to start llama-server automatically.\n"
        "Start manually with: ./scripts/start_server.sh\n"
        "Or run: llama-agent --setup to reconfigure"
    )
