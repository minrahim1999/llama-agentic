"""Tool registry: @tool decorator and schema generation."""

import inspect
import json
from typing import Callable, Any

_REGISTRY: dict[str, dict] = {}  # name → {fn, schema}


def tool(fn: Callable) -> Callable:
    """Register a function as an agent tool.

    The function's docstring (first line = description, Google-style Args:
    section for parameter descriptions) is used to build the JSON schema
    sent to the model.
    """
    schema = _build_schema(fn)
    _REGISTRY[fn.__name__] = {"fn": fn, "schema": schema}
    return fn


def get_all_schemas() -> list[dict]:
    """Return OpenAI-format tool schemas for all registered tools."""
    return [entry["schema"] for entry in _REGISTRY.values()]


def dispatch(name: str, arguments: str | dict) -> str:
    """Call a registered tool by name and return the string result."""
    if name not in _REGISTRY:
        return f"Error: unknown tool '{name}'"
    fn = _REGISTRY[name]["fn"]
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        result = fn(**args)
        output = str(result) if result is not None else "(no output)"
    except Exception as exc:
        return f"Error: {exc}"

    # Truncate to prevent context overflow
    from agent.config import config
    limit = config.tool_output_limit
    if limit > 0 and len(output) > limit:
        output = output[:limit] + f"\n...(truncated — {len(output)} chars total, limit {limit})"
    return output


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_PYTHON_TO_JSON = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
    "NoneType": "null",
}


def _build_schema(fn: Callable) -> dict:
    sig = inspect.signature(fn)
    doc = inspect.getdoc(fn) or ""
    description = doc.split("\n")[0]

    # Parse "Args:" block for per-param descriptions
    param_docs: dict[str, str] = {}
    in_args = False
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped == "Args:":
            in_args = True
            continue
        if in_args:
            if stripped and not stripped.startswith(" ") and stripped.endswith(":"):
                break  # new section
            if ":" in stripped:
                pname, pdesc = stripped.split(":", 1)
                param_docs[pname.strip()] = pdesc.strip()

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        ann = param.annotation
        json_type = "string"
        if ann != inspect.Parameter.empty:
            type_name = ann.__name__ if hasattr(ann, "__name__") else str(ann)
            json_type = _PYTHON_TO_JSON.get(type_name, "string")

        prop: dict[str, Any] = {"type": json_type}
        if name in param_docs:
            prop["description"] = param_docs[name]

        properties[name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
