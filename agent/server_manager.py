"""Auto-start / stop llama-server as a background subprocess.

Used when config.auto_start_server=True and the server is not already running.
"""

import atexit
import shutil
import signal
import subprocess
import time
from pathlib import Path

from agent.config import config
from agent.llama_client import check_server

_proc: subprocess.Popen | None = None


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
        model_path: Path to GGUF model. Falls back to model_cache_dir scan.
        wait_secs: Seconds to wait for server to become healthy.

    Returns True if server is up, False otherwise.
    """
    global _proc

    # Check if already running
    ok, _ = check_server()
    if ok:
        return True

    # Resolve model
    if not model_path:
        model_path = _find_model_file()
    if not model_path:
        return False

    # Resolve binary
    bin_path = shutil.which(config.llama_server_bin) or config.llama_server_bin
    if not shutil.which(bin_path):
        return False

    # Parse host/port from URL  (http://localhost:8080/v1 → 8080)
    port = 8080
    try:
        from urllib.parse import urlparse
        parsed = urlparse(config.llama_server_url)
        port = parsed.port or 8080
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
    model = model_path or _find_model_file()
    if not model:
        return False, (
            f"{msg}\n"
            f"No GGUF model found in {config.model_cache_dir}.\n"
            f"Download one with: llama-agent download <model>"
        )

    print(f"Starting llama-server with {Path(model).name} …", flush=True)
    started = start_server(model_path=model)
    if started:
        _, model_id = check_server()
        return True, model_id

    return False, (
        f"Failed to start llama-server automatically.\n"
        f"Start manually with: ./scripts/start_server.sh\n"
        f"Or run: llama-agent --setup to reconfigure"
    )
