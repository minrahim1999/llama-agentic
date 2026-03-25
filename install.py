#!/usr/bin/env python3
"""Cross-platform installer for llama-agentic.

Works on macOS, Linux, and Windows (Python 3.8+).
Installs the 'llama-agent' CLI globally using uv, pipx, or pip.

Usage:
    python install.py
    python install.py --help
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
MIN_PYTHON = (3, 11)


def banner(msg: str):
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}\n")


def ok(msg: str):
    print(f"  [OK]  {msg}")


def warn(msg: str):
    print(f"  [!!]  {msg}")


def fail(msg: str):
    print(f"  [XX]  {msg}")


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True)
    return subprocess.run(cmd, check=check)


# ── Python version check ─────────────────────────────────────────────────────

def check_python():
    v = sys.version_info[:2]
    if v < MIN_PYTHON:
        fail(f"Python {'.'.join(map(str, MIN_PYTHON))}+ required, found {'.'.join(map(str, v))}.")
        sys.exit(1)
    ok(f"Python {'.'.join(map(str, v))}")


# ── OS detection ─────────────────────────────────────────────────────────────

def detect_os() -> str:
    """Returns 'macos', 'linux', or 'windows'."""
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


# ── llama-server detection ───────────────────────────────────────────────────

_LLAMA_SEARCH_PATHS = {
    "macos": [
        "/opt/homebrew/bin/llama-server",
        "/usr/local/bin/llama-server",
    ],
    "linux": [
        "/usr/bin/llama-server",
        "/usr/local/bin/llama-server",
        "/snap/bin/llama-server",
    ],
    "windows": [
        r"C:\Program Files\llama.cpp\llama-server.exe",
        r"C:\llama.cpp\llama-server.exe",
    ],
}


def find_llama_server(os_name: str) -> str | None:
    # Check PATH first
    found = shutil.which("llama-server")
    if found:
        return found
    # Check well-known paths
    for p in _LLAMA_SEARCH_PATHS.get(os_name, []):
        if Path(p).exists():
            return p
    return None


def install_llama_cpp(os_name: str) -> bool:
    """Attempt to install llama.cpp. Returns True if successful."""
    print("\n  llama-server not found. Attempting automatic install…")
    if os_name == "macos":
        if shutil.which("brew"):
            print("  Running: brew install llama.cpp")
            result = run(["brew", "install", "llama.cpp"], check=False)
            return result.returncode == 0
        else:
            warn("Homebrew not found. Install it first: https://brew.sh")
            return False
    elif os_name == "linux":
        # Try apt (Debian/Ubuntu)
        if shutil.which("apt-get"):
            print("  Running: sudo apt-get install -y llama-cpp")
            result = run(["sudo", "apt-get", "install", "-y", "llama-cpp"], check=False)
            if result.returncode == 0:
                return True
        # Try snap
        if shutil.which("snap"):
            print("  Running: sudo snap install llama-cpp")
            result = run(["sudo", "snap", "install", "llama-cpp"], check=False)
            if result.returncode == 0:
                return True
        warn(
            "Could not auto-install llama.cpp.\n"
            "  Build from source: https://github.com/ggerganov/llama.cpp#build\n"
            "  Or install via your package manager."
        )
        return False
    elif os_name == "windows":
        # Try winget
        if shutil.which("winget"):
            print("  Running: winget install ggerganov.llama.cpp")
            result = run(["winget", "install", "-e", "--id", "ggerganov.llama.cpp"], check=False)
            return result.returncode == 0
        warn(
            "Could not auto-install llama.cpp on Windows.\n"
            "  Download prebuilt binaries from:\n"
            "  https://github.com/ggerganov/llama.cpp/releases\n"
            "  Then add the folder to your PATH."
        )
        return False
    return False


# ── Disk space check ─────────────────────────────────────────────────────────

def check_disk_space(min_gb: float = 5.0) -> tuple[float, bool]:
    """Check free disk space in home directory. Returns (free_gb, is_ok)."""
    try:
        stat = shutil.disk_usage(Path.home())
        free_gb = stat.free / (1024 ** 3)
        return free_gb, free_gb >= min_gb
    except Exception:
        return 0.0, True  # unknown — don't block


# ── Python package install ───────────────────────────────────────────────────

def install_package(editable: bool) -> bool:
    """Install llama-agentic using uv, pipx, or pip."""
    pkg = str(HERE) if editable else "llama-agentic"
    install_flag = ["--editable"] if editable else []

    if shutil.which("uv"):
        print("  Using: uv tool install")
        result = run(["uv", "tool", "install"] + install_flag + [pkg], check=False)
        if result.returncode == 0:
            return True
    if shutil.which("pipx"):
        print("  Using: pipx install")
        result = run(["pipx", "install"] + install_flag + [pkg], check=False)
        if result.returncode == 0:
            return True

    print("  Using: pip install (user)")
    result = run(
        [sys.executable, "-m", "pip", "install", "--user"] + install_flag + [pkg],
        check=False,
    )
    if result.returncode == 0:
        # Remind user about PATH
        home_bin = Path.home() / ".local" / "bin"
        print(f"\n  NOTE: Ensure {home_bin} is in your PATH:")
        print('    export PATH="$HOME/.local/bin:$PATH"')
        return True
    return False


# ── Global config writer ──────────────────────────────────────────────────────

GLOBAL_CONFIG_DIR = Path.home() / ".config" / "llama-agentic"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.env"
GLOBAL_DATA_DIR = Path.home() / ".local" / "share" / "llama-agentic"

_DEFAULT_MODEL_ALIAS = "qwen2.5-coder-3b"   # ~2 GB — sensible default
_DEFAULT_PORT = 11435


def write_global_config(model_name: str = _DEFAULT_MODEL_ALIAS) -> None:
    """Write ~/.config/llama-agentic/config.env with safe defaults."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    model_cache = GLOBAL_DATA_DIR / "models"

    GLOBAL_CONFIG_FILE.write_text(
        f"LLAMA_SERVER_URL=http://localhost:{_DEFAULT_PORT}/v1\n"
        f"LLAMA_MODEL={model_name}\n"
        f"LLAMA_CTX_SIZE=8192\n"
        f"LLAMA_N_GPU_LAYERS=-1\n"
        f"LLAMA_SERVER_BIN=llama-server\n"
        f"AUTO_START_SERVER=true\n"
        f"AUTO_STOP_SERVER=false\n"
        f"UNSAFE_MODE=false\n"
        f"MAX_TOOL_ITERATIONS=20\n"
        f"HISTORY_WINDOW=20\n"
        f"MODEL_CACHE_DIR={model_cache}\n",
        encoding="utf-8",
    )
    ok(f"Global config written: {GLOBAL_CONFIG_FILE}")


def auto_download_model(model_alias: str = _DEFAULT_MODEL_ALIAS) -> str | None:
    """Download a GGUF model using huggingface_hub. Returns local path or None."""
    # Known models (mirrors agent/model_manager.py to avoid import issues at install time)
    _KNOWN = {
        "qwen2.5-coder-7b": ("Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",  "qwen2.5-coder-7b-instruct-q4_k_m.gguf"),
        "qwen2.5-coder-3b": ("Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",  "qwen2.5-coder-3b-instruct-q4_k_m.gguf"),
        "llama3.2-3b":       ("bartowski/Llama-3.2-3B-Instruct-GGUF",  "Llama-3.2-3B-Instruct-Q4_K_M.gguf"),
        "mistral-7b":        ("TheBloke/Mistral-7B-Instruct-v0.2-GGUF","mistral-7b-instruct-v0.2.Q4_K_M.gguf"),
    }

    if model_alias not in _KNOWN:
        warn(f"Unknown model alias '{model_alias}'. Skipping download.")
        return None

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        warn("huggingface-hub not installed — cannot auto-download model.")
        warn("After install run:  llama-agent download " + model_alias)
        return None

    repo_id, filename = _KNOWN[model_alias]
    dest_dir = GLOBAL_DATA_DIR / "models"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Skip if already present
    target = dest_dir / filename
    if target.exists():
        ok(f"Model already cached: {target}")
        return str(target)

    print(f"\n  Downloading {model_alias} (~2 GB) from Hugging Face…")
    print(f"  Destination: {dest_dir}")
    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=str(dest_dir),
            local_dir_use_symlinks=False,
        )
        ok(f"Model downloaded: {path}")
        return path
    except Exception as e:
        warn(f"Download failed: {e}")
        warn("Try later:  llama-agent download " + model_alias)
        return None


# ── Post-install hint ─────────────────────────────────────────────────────────

def post_install_hints(os_name: str, llama_ok: bool, auto: bool):
    print("\n" + "─" * 60)
    print("  NEXT STEPS")
    print("─" * 60)
    if not llama_ok:
        warn("llama-server is not installed yet.")
        if os_name == "macos":
            print("    brew install llama.cpp")
        elif os_name == "linux":
            print("    sudo apt-get install llama-cpp  # or build from source")
        elif os_name == "windows":
            print("    winget install ggerganov.llama.cpp")
        print()
    if auto:
        print("  Just run:")
        print("       llama-agent")
        print()
    else:
        print("  1. Run the agent (first run starts setup wizard):")
        print("       llama-agent")
        print()
        print("  2. Download a model (if not done in setup wizard):")
        print("       llama-agent download qwen2.5-coder-3b")
        print()
    print("  Enable auto-start on boot:")
    print("       llama-agent autostart enable")
    print()
    print("  Check environment:")
    print("       llama-agent doctor")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Install llama-agentic")
    parser.add_argument("--no-llama",   action="store_true", help="Skip llama.cpp install check")
    parser.add_argument("--from-pypi",  action="store_true", help="Install from PyPI instead of local source")
    parser.add_argument("--auto",       action="store_true",
                        help="Non-interactive: create global config + download default model automatically")
    parser.add_argument("--model",      default=_DEFAULT_MODEL_ALIAS,
                        help=f"Model alias to download with --auto (default: {_DEFAULT_MODEL_ALIAS})")
    args = parser.parse_args()

    banner("llama-agentic installer")

    check_python()
    os_name = detect_os()
    ok(f"Platform: {os_name} ({platform.machine()})")

    # Disk space
    free_gb, space_ok = check_disk_space(min_gb=5.0)
    if space_ok:
        ok(f"Free disk space: {free_gb:.1f} GB")
    else:
        warn(f"Low disk space: {free_gb:.1f} GB free. Models need ~3-8 GB.")
        if not args.auto:
            answer = input("  Continue anyway? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                sys.exit(1)
        else:
            warn("Continuing in --auto mode despite low disk space.")

    # llama-server
    llama_ok = False
    if not args.no_llama:
        llama_bin = find_llama_server(os_name)
        if llama_bin:
            ok(f"llama-server: {llama_bin}")
            llama_ok = True
        else:
            installed = install_llama_cpp(os_name)
            if installed:
                llama_bin = find_llama_server(os_name)
                if llama_bin:
                    ok(f"llama-server installed: {llama_bin}")
                    llama_ok = True
                else:
                    warn("llama-server installed but not found in PATH yet. Restart your shell.")
            else:
                warn("llama-server not installed — you can install it later.")

    # Python package
    print("\n  Installing llama-agentic Python package…")
    editable = not args.from_pypi
    success = install_package(editable)
    if success:
        ok("llama-agentic installed. Command: llama-agent")
    else:
        fail("Installation failed. Try manually: pip install llama-agentic")
        sys.exit(1)

    # ── --auto: write global config + download model ──────────────────────────
    if args.auto:
        print()
        if GLOBAL_CONFIG_FILE.exists():
            ok(f"Global config already exists: {GLOBAL_CONFIG_FILE}  (skipping)")
        else:
            write_global_config(model_name=args.model)

        auto_download_model(model_alias=args.model)

    post_install_hints(os_name, llama_ok, auto=args.auto)
    banner("Install complete!")


if __name__ == "__main__":
    main()
