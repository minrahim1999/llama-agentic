"""Tests for the plugin loader."""

import sys
import tempfile
from pathlib import Path


def test_load_plugin_registers_tools(tmp_path):
    """A plugin file with @tool functions is loaded and tools are registered."""
    plugin_code = '''
from agent.tools import tool

@tool
def my_custom_tool(message: str) -> str:
    """A test custom tool.

    Args:
        message: The message to echo.
    """
    return f"echo: {message}"
'''
    plugin_file = tmp_path / "my_plugin.py"
    plugin_file.write_text(plugin_code)

    from agent.tools import _REGISTRY
    before = set(_REGISTRY.keys())

    from agent.plugins import load_plugins
    loaded = load_plugins(str(tmp_path))

    assert "my_plugin" in loaded
    assert "my_custom_tool" in _REGISTRY

    # Clean up
    _REGISTRY.pop("my_custom_tool", None)
    sys.modules.pop("plugins.my_plugin", None)


def test_skip_underscore_files(tmp_path):
    """Files starting with _ are not loaded."""
    plugin_code = '''
from agent.tools import tool

@tool
def hidden_tool() -> str:
    """Hidden."""
    return "hidden"
'''
    (tmp_path / "_disabled_plugin.py").write_text(plugin_code)

    from agent.plugins import load_plugins
    loaded = load_plugins(str(tmp_path))

    assert "_disabled_plugin" not in loaded
    assert "disabled_plugin" not in loaded

    from agent.tools import _REGISTRY
    assert "hidden_tool" not in _REGISTRY


def test_load_missing_dir():
    """Loading from a non-existent directory returns empty list gracefully."""
    from agent.plugins import load_plugins
    result = load_plugins("/tmp/definitely_does_not_exist_xyzzy")
    assert result == []


def test_plugin_error_does_not_crash(tmp_path):
    """A plugin with a syntax error is skipped, not fatal."""
    (tmp_path / "broken_plugin.py").write_text("this is not valid python !!!")

    from agent.plugins import load_plugins
    loaded = load_plugins(str(tmp_path))  # should not raise
    assert "broken_plugin" not in loaded


def test_example_plugin_tools():
    """The bundled example plugin exposes expected tools."""
    from agent.plugins import load_plugins
    load_plugins("plugins")  # load from real plugins/ dir

    from agent.tools import _REGISTRY
    assert "get_current_dir" in _REGISTRY
    assert "count_words" in _REGISTRY


def test_example_plugin_works():
    """Example plugin tools actually run correctly."""
    from agent.plugins import load_plugins
    load_plugins("plugins")

    from agent.tools import dispatch
    result = dispatch("count_words", '{"text": "hello world foo"}')
    assert "Words: 3" in result

    result2 = dispatch("get_current_dir", "{}")
    assert "/" in result2  # returns a path
