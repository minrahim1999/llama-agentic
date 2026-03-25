"""Register / unregister llama-server as a system boot service.

- macOS  : launchd user agent   (~/.config/launchd/... via ~/Library/LaunchAgents/)
- Linux  : systemd user service (~/.config/systemd/user/)
- Windows: Task Scheduler       (schtasks /create)
"""

import platform
import shutil
import subprocess
from pathlib import Path


def _os() -> str:
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


def _find_model() -> str | None:
    """Return the configured GGUF path, falling back to the model cache."""
    try:
        from agent.server_manager import resolve_model_file
        return resolve_model_file()
    except Exception:
        return None


def _find_llama_server() -> str | None:
    found = shutil.which("llama-server")
    if found:
        return found
    for p in [
        "/opt/homebrew/bin/llama-server",
        "/usr/local/bin/llama-server",
        "/usr/bin/llama-server",
    ]:
        if Path(p).exists():
            return p
    return None


def _parse_port() -> int:
    try:
        from agent.config import config
        from urllib.parse import urlparse
        return urlparse(config.llama_server_url).port or 11435
    except Exception:
        return 11435


# ── macOS launchd ─────────────────────────────────────────────────────────────

_MACOS_PLIST_ID = "com.llama-agentic.server"
_MACOS_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_MACOS_PLIST_ID}.plist"


def _macos_plist(llama_bin: str, model_path: str, port: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_MACOS_PLIST_ID}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{llama_bin}</string>
        <string>--model</string>
        <string>{model_path}</string>
        <string>--port</string>
        <string>{port}</string>
        <string>--ctx-size</string>
        <string>8192</string>
        <string>--n-gpu-layers</string>
        <string>-1</string>
        <string>--jinja</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/.local/share/llama-agentic/server.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/.local/share/llama-agentic/server.log</string>
</dict>
</plist>
"""


def _enable_macos(llama_bin: str, model_path: str, port: int) -> str:
    _MACOS_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path.home() / ".local" / "share" / "llama-agentic"
    log_dir.mkdir(parents=True, exist_ok=True)

    _MACOS_PLIST_PATH.write_text(_macos_plist(llama_bin, model_path, port))

    # Unload if already loaded (ignore errors)
    subprocess.run(
        ["launchctl", "unload", str(_MACOS_PLIST_PATH)],
        capture_output=True,
    )
    result = subprocess.run(
        ["launchctl", "load", "-w", str(_MACOS_PLIST_PATH)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"launchctl load failed: {result.stderr.strip()}")
    return f"LaunchAgent installed: {_MACOS_PLIST_PATH}"


def _disable_macos() -> str:
    if _MACOS_PLIST_PATH.exists():
        subprocess.run(
            ["launchctl", "unload", "-w", str(_MACOS_PLIST_PATH)],
            capture_output=True,
        )
        _MACOS_PLIST_PATH.unlink()
        return f"LaunchAgent removed: {_MACOS_PLIST_PATH}"
    return "No LaunchAgent found."


# ── Linux systemd ─────────────────────────────────────────────────────────────

_SYSTEMD_UNIT = "llama-agentic-server.service"
_SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
_SYSTEMD_PATH = _SYSTEMD_DIR / _SYSTEMD_UNIT


def _systemd_unit(llama_bin: str, model_path: str, port: int) -> str:
    return f"""[Unit]
Description=llama-agentic LLM server
After=network.target

[Service]
Type=simple
ExecStart={llama_bin} --model {model_path} --port {port} --ctx-size 8192 --n-gpu-layers -1 --jinja
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def _enable_linux(llama_bin: str, model_path: str, port: int) -> str:
    _SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    _SYSTEMD_PATH.write_text(_systemd_unit(llama_bin, model_path, port))

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", _SYSTEMD_UNIT], check=True)
    # Enable linger so the service starts even before login (optional, requires sudo)
    try:
        subprocess.run(
            ["loginctl", "enable-linger", Path.home().name],
            capture_output=True,
        )
    except Exception:
        pass
    return f"systemd user service enabled: {_SYSTEMD_PATH}"


def _disable_linux() -> str:
    if _SYSTEMD_PATH.exists():
        subprocess.run(["systemctl", "--user", "disable", "--now", _SYSTEMD_UNIT], capture_output=True)
        _SYSTEMD_PATH.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        return f"systemd service removed: {_SYSTEMD_PATH}"
    return "No systemd service found."


# ── Windows Task Scheduler ────────────────────────────────────────────────────

_WIN_TASK_NAME = "llama-agentic-server"


def _enable_windows(llama_bin: str, model_path: str, port: int) -> str:
    cmd = (
        f'"{llama_bin}" --model "{model_path}" '
        f"--port {port} --ctx-size 8192 --n-gpu-layers -1 --jinja"
    )
    result = subprocess.run(
        [
            "schtasks", "/create", "/f",
            "/tn", _WIN_TASK_NAME,
            "/tr", cmd,
            "/sc", "ONLOGON",
            "/rl", "HIGHEST",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"schtasks failed: {result.stderr.strip()}")
    return f"Task Scheduler entry created: {_WIN_TASK_NAME}"


def _disable_windows() -> str:
    result = subprocess.run(
        ["schtasks", "/delete", "/f", "/tn", _WIN_TASK_NAME],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return f"Task Scheduler entry removed: {_WIN_TASK_NAME}"
    return "No Task Scheduler entry found."


# ── Public API ────────────────────────────────────────────────────────────────

def enable(model_path: str | None = None) -> str:
    """Register llama-server as a boot service. Returns a status message."""
    os_name = _os()
    port = _parse_port()

    llama_bin = _find_llama_server()
    if not llama_bin:
        raise RuntimeError(
            "llama-server binary not found in PATH.\n"
            "Install llama.cpp first, then re-run: llama-agent autostart enable"
        )

    if not model_path:
        model_path = _find_model()
    if not model_path:
        raise RuntimeError(
            "No GGUF model found in cache.\n"
            "Download one first: llama-agent download qwen2.5-coder-7b"
        )

    if os_name == "macos":
        return _enable_macos(llama_bin, model_path, port)
    elif os_name == "linux":
        return _enable_linux(llama_bin, model_path, port)
    else:
        return _enable_windows(llama_bin, model_path, port)


def disable() -> str:
    """Remove the boot service entry. Returns a status message."""
    os_name = _os()
    if os_name == "macos":
        return _disable_macos()
    elif os_name == "linux":
        return _disable_linux()
    else:
        return _disable_windows()


def status() -> str:
    """Return a human-readable status of the boot service."""
    os_name = _os()
    if os_name == "macos":
        if _MACOS_PLIST_PATH.exists():
            return f"Enabled  (LaunchAgent: {_MACOS_PLIST_PATH})"
        return "Disabled (no LaunchAgent found)"
    elif os_name == "linux":
        if _SYSTEMD_PATH.exists():
            result = subprocess.run(
                ["systemctl", "--user", "is-active", _SYSTEMD_UNIT],
                capture_output=True, text=True,
            )
            state = result.stdout.strip()
            return f"Enabled  (systemd unit: {_SYSTEMD_PATH}, state: {state})"
        return "Disabled (no systemd unit found)"
    else:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", _WIN_TASK_NAME],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return f"Enabled  (Task Scheduler: {_WIN_TASK_NAME})"
        return "Disabled (no Task Scheduler entry)"
