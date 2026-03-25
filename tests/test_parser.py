"""Tests for content-based tool call parser."""

from agent.core import _parse_content_tool_calls, _strip_tool_call_markup


def test_qwen_functioncalls_tag():
    text = '<functionCalls>\n{"name": "list_dir", "arguments": {"path": "."}}\n</functionCalls>'
    calls = _parse_content_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "list_dir"
    import json
    args = json.loads(calls[0].function.arguments)
    assert args["path"] == "."


def test_function_call_tag():
    text = '```xml\n<function_call>\n  {"name": "read_file", "arguments": {"path": "main.py"}}\n</function_call>\n```'
    calls = _parse_content_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "read_file"


def test_json_code_block():
    text = '```json\n{"name": "run_python", "arguments": {"code": "print(1)"}}\n```'
    calls = _parse_content_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "run_python"


def test_no_tool_call():
    text = "Here is a friendly answer with no tool calls."
    calls = _parse_content_tool_calls(text)
    assert calls == []


def test_strip_markup():
    text = 'I will list the files.\n<functionCalls>\n{"name": "list_dir", "arguments": {"path": "."}}\n</functionCalls>\nDone.'
    stripped = _strip_tool_call_markup(text)
    assert "functionCalls" not in stripped
    assert "list_dir" not in stripped
    assert "I will list the files." in stripped
