"""Tests for the plugin loader."""

import sys


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
    from agent.plugins import load_plugins
    loaded = load_plugins(str(tmp_path))

    assert "my_plugin" in loaded
    assert "my_custom_tool" in _REGISTRY

    # Clean up
    _REGISTRY.pop("my_custom_tool", None)
    for name in list(sys.modules):
        if "my_plugin" in name:
            sys.modules.pop(name, None)


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


def test_default_load_uses_configured_user_plugin_dir(tmp_path, monkeypatch):
    plugin_code = '''
from agent.tools import tool

@tool
def user_plugin_tool() -> str:
    """User plugin."""
    return "user"
'''
    user_dir = tmp_path / "user-plugins"
    user_dir.mkdir()
    (user_dir / "user_plugin.py").write_text(plugin_code)

    from agent.config import config
    from agent.plugins import load_plugins

    monkeypatch.setattr(config, "plugins_dir", str(user_dir))
    monkeypatch.setattr(config, "enable_project_plugins", False)

    loaded = load_plugins()

    from agent.tools import _REGISTRY
    assert "user_plugin" in loaded
    assert "user_plugin_tool" in _REGISTRY
    _REGISTRY.pop("user_plugin_tool", None)

    for name in list(sys.modules):
        if "user_plugin" in name:
            sys.modules.pop(name, None)


def test_default_load_does_not_import_cwd_plugins_without_opt_in(tmp_path, monkeypatch):
    plugin_code = '''
from agent.tools import tool

@tool
def project_plugin_tool() -> str:
    """Project plugin."""
    return "project"
'''
    cwd_plugins = tmp_path / "plugins"
    cwd_plugins.mkdir()
    (cwd_plugins / "unsafe_plugin.py").write_text(plugin_code)

    project_plugins = tmp_path / ".llama-agentic" / "plugins"
    project_plugins.mkdir(parents=True)
    (project_plugins / "project_plugin.py").write_text(plugin_code)

    monkeypatch.chdir(tmp_path)

    from agent.config import config
    from agent.plugins import load_plugins
    from agent.tools import _REGISTRY

    monkeypatch.setattr(config, "plugins_dir", str(tmp_path / "no-user-plugins"))
    monkeypatch.setattr(config, "enable_project_plugins", False)

    loaded = load_plugins()
    assert loaded == []
    assert "project_plugin_tool" not in _REGISTRY

    monkeypatch.setattr(config, "enable_project_plugins", True)
    loaded = load_plugins()
    assert "project_plugin" in loaded
    assert "project_plugin_tool" in _REGISTRY
    assert "unsafe_plugin" not in loaded
    _REGISTRY.pop("project_plugin_tool", None)

    for name in list(sys.modules):
        if "project_plugin" in name or "unsafe_plugin" in name:
            sys.modules.pop(name, None)


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
