"""Plugin loader with explicit, safe plugin search paths."""

import hashlib
import importlib.util
import sys
from pathlib import Path

from agent.config import config


def _default_plugin_dirs() -> list[Path]:
    dirs = [Path(config.plugins_dir).expanduser()]
    if config.enable_project_plugins:
        dirs.append(Path.cwd() / ".llama-agentic" / "plugins")
    return dirs


def _iter_plugin_dirs(plugins_dir: str | Path | list[str | Path] | tuple[str | Path, ...] | None) -> list[Path]:
    if plugins_dir is None:
        return _default_plugin_dirs()
    if isinstance(plugins_dir, (list, tuple)):
        return [Path(p).expanduser() for p in plugins_dir]
    return [Path(plugins_dir).expanduser()]


def _module_name_for(py_file: Path) -> str:
    digest = hashlib.md5(str(py_file.resolve()).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"_llama_agentic_plugin_{py_file.stem}_{digest}"


def load_plugins(plugins_dir: str | Path | list[str | Path] | tuple[str | Path, ...] | None = None) -> list[str]:
    """Scan one or more plugin directories and import their plugin modules.

    When no directory is provided, plugins are loaded only from safe,
    explicitly configured locations:
      - `config.plugins_dir`
      - `.llama-agentic/plugins` when `enable_project_plugins=true`

    Returns list of loaded plugin stem names.
    Files starting with '_' are skipped (treat as private/disabled).
    """
    loaded: list[str] = []
    for plugin_path in _iter_plugin_dirs(plugins_dir):
        if not plugin_path.exists():
            continue

        for py_file in sorted(plugin_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = _module_name_for(py_file)
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                loaded.append(py_file.stem)
            except Exception as exc:
                print(f"[plugins] Failed to load {py_file.name}: {exc}")

    return loaded
