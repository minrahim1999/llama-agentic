"""Configuration — global defaults + per-project overrides.

Config hierarchy (later files override earlier):
  1. ~/.config/llama-agentic/config.env   (global defaults, created by setup wizard)
  2. ./.env                               (project-level overrides)
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

GLOBAL_CONFIG_DIR = Path.home() / ".config" / "llama-agentic"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.env"
GLOBAL_DATA_DIR = Path.home() / ".local" / "share" / "llama-agentic"

# Determine env files to load (global first, local overrides)
_env_files: list[str] = []
if GLOBAL_CONFIG_FILE.exists():
    _env_files.append(str(GLOBAL_CONFIG_FILE))
_local_env = Path(".env")
if _local_env.exists():
    _env_files.append(str(_local_env))
if not _env_files:
    _env_files = [".env"]  # pydantic-settings ignores missing files gracefully


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llama_server_url: str = "http://localhost:11435/v1"
    llama_model: str = "local-model"
    llama_model_path: str = ""
    llama_ctx_size: int = 8192
    llama_n_gpu_layers: int = -1

    # Agent behaviour
    max_tool_iterations: int = 20
    unsafe_mode: bool = False
    stream: bool = True
    max_output_tokens: int = 2048
    history_window: int = 20

    # Tool output — cap to prevent context overflow
    tool_output_limit: int = 8000  # chars; 0 = unlimited

    # Server management
    auto_start_server: bool = True
    auto_stop_server: bool = False
    llama_server_bin: str = "llama-server"  # path or name in PATH

    # Model cache
    model_cache_dir: str = str(GLOBAL_DATA_DIR / "models")

    # Data dirs — default to global, overridable per-project via env
    memory_dir: str = str(GLOBAL_DATA_DIR / "memory")
    sessions_dir: str = str(GLOBAL_DATA_DIR / "sessions")

    # Plugin loading — safe by default
    plugins_dir: str = str(GLOBAL_CONFIG_DIR / "plugins")
    enable_project_plugins: bool = False

    # Agent mode: chat | plan | code | hybrid | review  (default: hybrid)
    agent_mode: str = "hybrid"


config = Config()


def is_first_run() -> bool:
    """True if no global config file exists yet."""
    return not GLOBAL_CONFIG_FILE.exists()


def use_project_data_dirs():
    """Switch memory/sessions to .llama-agentic/ in the current directory."""
    cwd = Path.cwd() / ".llama-agentic"
    config.memory_dir = str(cwd / "memory")
    config.sessions_dir = str(cwd / "sessions")


def configured_model_path() -> Path | None:
    """Return the configured GGUF path if set and it exists."""
    if not config.llama_model_path:
        return None
    path = Path(config.llama_model_path).expanduser()
    if path.exists():
        return path.resolve()
    return None


def update_global_config_values(updates: dict[str, str | int | bool]) -> None:
    """Merge key/value updates into the global config.env file."""
    existing: dict[str, str] = {}
    if GLOBAL_CONFIG_FILE.exists():
        for line in GLOBAL_CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            existing[key] = value

    for key, value in updates.items():
        if isinstance(value, bool):
            existing[key] = "true" if value else "false"
        else:
            existing[key] = str(value)

    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in existing.items()]
    GLOBAL_CONFIG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
