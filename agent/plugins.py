"""Plugin loader — auto-imports .py files from the plugins/ directory.

Drop any Python file into plugins/ and define functions with @tool to add
custom tools without touching the core codebase.
"""

import importlib.util
import sys
from pathlib import Path


def load_plugins(plugins_dir: str = "plugins") -> list[str]:
    """Scan plugins_dir for .py files and import them.

    Returns list of loaded plugin module names.
    Files starting with '_' are skipped (treat as private/disabled).
    """
    p = Path(plugins_dir)
    if not p.exists():
        return []

    loaded: list[str] = []
    for py_file in sorted(p.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"plugins.{py_file.stem}"
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
