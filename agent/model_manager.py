"""Download GGUF models from Hugging Face Hub into model_cache_dir."""

from pathlib import Path


# Well-known models: short alias → (repo_id, filename)
KNOWN_MODELS: dict[str, tuple[str, str]] = {
    "qwen2.5-coder-7b": (
        "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
        "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
    ),
    "qwen2.5-coder-3b": (
        "Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
        "qwen2.5-coder-3b-instruct-q4_k_m.gguf",
    ),
    "llama3.2-3b": (
        "bartowski/Llama-3.2-3B-Instruct-GGUF",
        "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
    ),
    "mistral-7b": (
        "TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
        "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
    ),
    "deepseek-coder-7b": (
        "TheBloke/deepseek-coder-7B-instruct-GGUF",
        "deepseek-coder-7b-instruct.Q4_K_M.gguf",
    ),
}


def list_known() -> list[str]:
    """Return list of known model aliases."""
    return list(KNOWN_MODELS.keys())


def download(
    alias_or_repo: str,
    filename: str | None = None,
    dest_dir: str | None = None,
    show_progress: bool = True,
) -> str:
    """Download a GGUF model to dest_dir (defaults to config.model_cache_dir).

    Args:
        alias_or_repo: Short alias (e.g. 'qwen2.5-coder-7b') or HF repo ID.
        filename: Filename within the repo (required if using raw repo ID).
        dest_dir: Override destination directory.
        show_progress: Show download progress bar.

    Returns the local path to the downloaded file.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise RuntimeError(
            "huggingface-hub is not installed.\n"
            "Install it with: pip install huggingface-hub"
        )

    from agent.config import config

    cache = Path(dest_dir or config.model_cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    # Resolve alias
    if alias_or_repo in KNOWN_MODELS:
        repo_id, fname = KNOWN_MODELS[alias_or_repo]
    else:
        repo_id = alias_or_repo
        fname = filename
        if not fname:
            raise ValueError(
                f"Unknown alias '{alias_or_repo}'.\n"
                f"For a raw repo ID, provide --filename.\n"
                f"Known aliases: {', '.join(KNOWN_MODELS)}"
            )

    local_path = hf_hub_download(
        repo_id=repo_id,
        filename=fname,
        local_dir=str(cache),
        local_dir_use_symlinks=False,
    )
    return local_path


def find_models(model_dir: str | None = None) -> list[Path]:
    """Return all .gguf files found in model_cache_dir."""
    from agent.config import config

    cache = Path(model_dir or config.model_cache_dir)
    if not cache.exists():
        return []
    return sorted(cache.glob("**/*.gguf"))
