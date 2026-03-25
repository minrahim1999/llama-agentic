# Plugin Development

Plugins let you add custom tools to the agent without modifying the core codebase. Put a `.py` file in your configured plugin directory and it is loaded at startup. Per-project plugins are supported only when `ENABLE_PROJECT_PLUGINS=true`.

---

## Quick start

Create `~/.config/llama-agentic/plugins/my_tools.py`:

```python
from agent.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City name to look up.
    """
    # Replace with a real API call
    return f"Weather in {city}: sunny, 22°C"
```

Restart the agent — the tool appears in `/tools`:

```
/tools
  get_weather    Get the current weather for a city.
```

---

## The `@tool` decorator

The `@tool` decorator:

1. Registers the function in the global tool registry
2. Auto-generates the OpenAI function-calling JSON schema from the function signature and docstring
3. Makes the tool available to the LLM in every turn

### Signature rules

- Parameters become required fields in the schema (unless they have a default value)
- Type annotations (`str`, `int`, `float`, `bool`, `list`, `dict`) map to JSON schema types
- Parameters without type annotations default to `"string"` type

### Docstring format (Google style)

```python
@tool
def my_tool(param1: str, param2: int = 5) -> str:
    """Short one-line description used as the tool description.

    Longer explanation goes here (optional, not shown in schema).

    Args:
        param1: Description of the first parameter.
        param2: Description of the second parameter (has default = optional).
    """
    ...
```

---

## Examples

### File utility

```python
from agent.tools import tool
from pathlib import Path


@tool
def count_lines(path: str) -> str:
    """Count the number of lines in a file.

    Args:
        path: Path to the file.
    """
    try:
        n = len(Path(path).read_text(encoding="utf-8").splitlines())
        return f"{n} lines in {path}"
    except Exception as exc:
        return f"Error: {exc}"
```

### HTTP API call

```python
import httpx
from agent.tools import tool


@tool
def get_github_user(username: str) -> str:
    """Fetch public info about a GitHub user.

    Args:
        username: GitHub username to look up.
    """
    try:
        resp = httpx.get(f"https://api.github.com/users/{username}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return (
            f"Name: {data.get('name')}\n"
            f"Bio: {data.get('bio')}\n"
            f"Public repos: {data.get('public_repos')}\n"
            f"Followers: {data.get('followers')}"
        )
    except Exception as exc:
        return f"Error: {exc}"
```

### Subprocess tool

```python
import subprocess
from agent.tools import tool


@tool
def run_pytest(path: str = "tests/") -> str:
    """Run pytest on a path and return the summary.

    Args:
        path: Directory or file to run tests on.
    """
    result = subprocess.run(
        ["python", "-m", "pytest", path, "--tb=short", "-q"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    return output[-3000:] if len(output) > 3000 else output
```

### Tool with optional parameters

```python
from agent.tools import tool


@tool
def search_code(pattern: str, path: str = ".", file_glob: str = "*.py") -> str:
    """Search for a pattern in source files using grep.

    Args:
        pattern: Regular expression to search for.
        path: Directory to search in (default: current directory).
        file_glob: File pattern to match (default: *.py).
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "--include", file_glob, pattern, path],
        capture_output=True, text=True,
    )
    if result.returncode == 1:
        return "No matches found."
    return result.stdout[:4000] if result.stdout else result.stderr
```

---

## Tool return values

Tools must return a string. The string is injected into the conversation as the tool's observation.

- Return descriptive success messages: `"Written 512 chars to summary.md"`
- Return errors with an `"Error: ..."` prefix — the agent detects this and shows a red indicator
- Return empty string `""` if no output is meaningful (the agent handles it gracefully)

---

## Disabling a plugin

Prefix the filename with `_` to prevent it from loading:

```bash
mv ~/.config/llama-agentic/plugins/my_tools.py ~/.config/llama-agentic/plugins/_my_tools.py
```

---

## Plugin loading order

Plugins are loaded in alphabetical filename order, after all built-in tools. If a plugin registers a tool with the same name as a built-in, the plugin version wins.

---

## Accessing config from a plugin

```python
from agent.config import config

@tool
def show_model() -> str:
    """Show the currently configured model name."""
    return f"Active model: {config.llama_model}"
```

---

## Error handling

Wrap tool code in try/except and return `"Error: ..."` strings rather than raising exceptions. The tool dispatcher catches all exceptions anyway, but explicit error messages are more informative.

```python
@tool
def safe_read(path: str) -> str:
    """Read a file safely.

    Args:
        path: File path to read.
    """
    try:
        from pathlib import Path
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except PermissionError:
        return f"Error: permission denied: {path}"
    except Exception as exc:
        return f"Error: {exc}"
```
