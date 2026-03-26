"""Unit tests for the ReAct agent core loop."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent():
    """Create an Agent with no MCP loading and no confirmation prompts."""
    with patch("agent.core.get_client"), \
         patch("agent.core.load_plugins", return_value=[]):
        from agent.core import Agent
        return Agent(confirm_callback=None, load_mcp=False)


def _fake_stream(text: str = "", tool_calls: list | None = None):
    """Build a fake streaming response mimicking openai stream chunks."""
    chunks = []

    if text:
        for word in text.split(" "):
            chunk = SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=word + " ", tool_calls=None)
                )]
            )
            chunks.append(chunk)

    if tool_calls:
        for i, tc in enumerate(tool_calls):
            chunk = SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[SimpleNamespace(
                            index=i,
                            id=f"call_{i}",
                            function=SimpleNamespace(
                                name=tc["name"],
                                arguments=json.dumps(tc["arguments"]),
                            ),
                        )],
                    )
                )]
            )
            chunks.append(chunk)

    return iter(chunks)


# ---------------------------------------------------------------------------
# Tests: history management
# ---------------------------------------------------------------------------

def test_agent_initial_state():
    agent = _make_agent()
    assert agent.history == []
    assert "tools" in agent.system_prompt.lower() or "assistant" in agent.system_prompt.lower()


def test_reset_clears_history():
    agent = _make_agent()
    agent.history = [{"role": "user", "content": "hi"}]
    agent.reset()
    assert agent.history == []


def test_windowed_history_empty():
    agent = _make_agent()
    assert agent._windowed_history() == []


def test_windowed_history_within_limit():
    agent = _make_agent()
    agent.history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    windowed = agent._windowed_history()
    assert len(windowed) == 4


def test_windowed_history_trims_oldest_turns():
    from agent.config import config
    agent = _make_agent()
    config.history_window = 2

    # 4 user turns
    for i in range(4):
        agent.history.append({"role": "user", "content": f"q{i}"})
        agent.history.append({"role": "assistant", "content": f"a{i}"})

    windowed = agent._windowed_history()
    # Only last 2 turns should be kept
    roles = [m["role"] for m in windowed]
    assert roles.count("user") == 2
    # The last user message should be q3
    user_msgs = [m for m in windowed if m["role"] == "user"]
    assert user_msgs[-1]["content"] == "q3"


def test_windowed_history_unlimited():
    from agent.config import config
    agent = _make_agent()
    config.history_window = 0  # unlimited

    for i in range(30):
        agent.history.append({"role": "user", "content": f"q{i}"})
        agent.history.append({"role": "assistant", "content": f"a{i}"})

    windowed = agent._windowed_history()
    assert len(windowed) == 60


# ---------------------------------------------------------------------------
# Tests: tool dispatch in run()
# ---------------------------------------------------------------------------

def test_run_plain_text_response():
    """Agent yields text when LLM returns no tool calls."""
    agent = _make_agent()

    mock_stream = _fake_stream(text="Hello world")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_stream
    agent.client = mock_client

    chunks = list(agent.run("hi"))
    full = "".join(chunks).strip()
    assert "Hello" in full
    assert len(agent.history) == 2  # user + assistant


def test_run_appends_user_message():
    agent = _make_agent()

    mock_stream = _fake_stream(text="response")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_stream
    agent.client = mock_client

    list(agent.run("test input"))
    assert agent.history[0]["role"] == "user"
    assert agent.history[0]["content"] == "test input"


def test_run_tool_call_dispatched():
    """Agent calls a tool when LLM returns a tool_calls response."""
    import agent.tools.code  # noqa: F401 — ensure run_python is registered

    agent = _make_agent()
    agent.history = []

    # First call: returns a tool_call for run_python
    stream1 = _fake_stream(tool_calls=[{"name": "run_python", "arguments": {"code": "print(99)"}}])
    # Second call: plain text after tool observation
    stream2 = _fake_stream(text="The result is 99")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [stream1, stream2]
    agent.client = mock_client

    "".join(list(agent.run("run python")))

    # Should have called the tool and gotten 99 in the observation
    tool_msgs = [m for m in agent.history if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "99" in tool_msgs[0]["content"]


def test_run_suppresses_pre_tool_planning_text():
    """Assistant planning text should not be surfaced when a tool runs."""
    import agent.tools.code  # noqa: F401 — ensure run_python is registered

    agent = _make_agent()
    stream1 = _fake_stream(
        text="I will run Python first.",
        tool_calls=[{"name": "run_python", "arguments": {"code": "print(7)"}}],
    )
    stream2 = _fake_stream(text="Done.")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [stream1, stream2]
    agent.client = mock_client

    output = "".join(list(agent.run("do it")))

    assert "I will run Python first." not in output
    assert "Done." in output


def test_run_confirmation_callback_deny():
    """When confirmation callback returns False, tool is not executed."""
    import agent.tools.code  # noqa: F401

    deny_cb = MagicMock(return_value=False)
    agent = _make_agent()
    agent.confirm_callback = deny_cb

    stream1 = _fake_stream(tool_calls=[{"name": "run_python", "arguments": {"code": "print(1)"}}])
    stream2 = _fake_stream(text="OK")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [stream1, stream2]
    agent.client = mock_client

    from agent.config import config
    orig = config.unsafe_mode
    config.unsafe_mode = False

    list(agent.run("do something"))

    tool_msgs = [m for m in agent.history if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "declined" in tool_msgs[0]["content"].lower()

    config.unsafe_mode = orig


def test_run_confirmation_callback_approve():
    """When confirmation callback returns True, tool IS executed."""
    import agent.tools.code  # noqa: F401

    approve_cb = MagicMock(return_value=True)
    agent = _make_agent()
    agent.confirm_callback = approve_cb

    stream1 = _fake_stream(tool_calls=[{"name": "run_python", "arguments": {"code": "print(42)"}}])
    stream2 = _fake_stream(text="Done")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [stream1, stream2]
    agent.client = mock_client

    from agent.config import config
    orig = config.unsafe_mode
    config.unsafe_mode = False

    list(agent.run("execute"))

    tool_msgs = [m for m in agent.history if m["role"] == "tool"]
    assert "42" in tool_msgs[0]["content"]

    config.unsafe_mode = orig


# ---------------------------------------------------------------------------
# Tests: content-based tool call parser
# ---------------------------------------------------------------------------

def test_parse_xml_function_calls():
    from agent.core import _parse_content_tool_calls

    text = '<functionCalls>{"name": "read_file", "arguments": {"path": "/tmp/x.txt"}}</functionCalls>'
    calls = _parse_content_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "read_file"


def test_parse_json_code_block():
    from agent.core import _parse_content_tool_calls

    text = '```json\n{"name": "list_dir", "arguments": {"path": "/tmp"}}\n```'
    calls = _parse_content_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "list_dir"


def test_parse_double_brace_tool_call():
    from agent.core import _parse_content_tool_calls

    text = '{{"name": "run_shell", "arguments": {"command": "pwd", "cwd": "."}}}'
    calls = _parse_content_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "run_shell"
    assert '"command": "pwd"' in calls[0].function.arguments


def test_parse_tool_call_list_payload():
    from agent.core import _parse_content_tool_calls

    text = (
        '[{"name": "make_dir", "arguments": {"path": "src"}}, '
        '{"name": "write_file", "arguments": {"path": "src/a.txt", "content": "x"}}]'
    )
    calls = _parse_content_tool_calls(text)
    assert [call.function.name for call in calls] == ["make_dir", "write_file"]


def test_parse_deduplicates():
    from agent.core import _parse_content_tool_calls

    text = (
        '<functionCalls>{"name": "git_status", "arguments": {}}</functionCalls>'
        '<function_call>{"name": "git_status", "arguments": {}}</function_call>'
    )
    calls = _parse_content_tool_calls(text)
    assert len(calls) == 1


def test_parse_no_tool_calls():
    from agent.core import _parse_content_tool_calls

    calls = _parse_content_tool_calls("Just a normal text response with no tool calls.")
    assert calls == []


def test_strip_tool_call_markup():
    from agent.core import _strip_tool_call_markup

    text = 'Thinking...\n<functionCalls>{"name": "x", "arguments": {}}</functionCalls>\nDone.'
    stripped = _strip_tool_call_markup(text)
    assert "functionCalls" not in stripped
    assert "Thinking" in stripped


def test_strip_double_brace_tool_call_markup():
    from agent.core import _strip_tool_call_markup

    text = 'Creating project\n{{"name": "write_file", "arguments": {"path": "a.txt", "content": "hi"}}}\nDone.'
    stripped = _strip_tool_call_markup(text)
    assert "write_file" not in stripped
    assert "Creating project" in stripped
    assert "Done." in stripped


# ---------------------------------------------------------------------------
# Tests: parallel tool dispatch
# ---------------------------------------------------------------------------

def test_parallel_dispatch_results_in_order():
    """Multiple non-confirm tool calls are dispatched and results arrive in order."""
    import agent.tools.file  # noqa: F401 — ensure read_file is registered
    import agent.tools.git   # noqa: F401 — ensure git_status is registered

    agent = _make_agent()
    agent.history = []

    # Two non-mutating tool calls in one response
    stream1 = _fake_stream(tool_calls=[
        {"name": "git_status",  "arguments": {}},
        {"name": "git_status",  "arguments": {}},
    ])
    stream2 = _fake_stream(text="Done")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [stream1, stream2]
    agent.client = mock_client

    output = "".join(list(agent.run("check repo")))

    tool_msgs = [m for m in agent.history if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    # Both tool_call_ids should be distinct call_0 and call_1
    ids = [m["tool_call_id"] for m in tool_msgs]
    assert ids == ["call_0", "call_1"]


def test_parallel_dispatch_does_not_parallelize_confirm_tools():
    """CONFIRM_TOOLS are never sent to the thread pool — confirm callback is called."""
    import agent.tools.code  # noqa: F401

    call_order: list[str] = []

    def tracking_cb(name, args):
        call_order.append(f"confirm:{name}")
        return True

    agent = _make_agent()
    agent.confirm_callback = tracking_cb

    stream1 = _fake_stream(tool_calls=[
        {"name": "run_python", "arguments": {"code": "print(1)"}},
        {"name": "run_python", "arguments": {"code": "print(2)"}},
    ])
    stream2 = _fake_stream(text="Done")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [stream1, stream2]
    agent.client = mock_client

    from agent.config import config
    orig = config.unsafe_mode
    config.unsafe_mode = False
    list(agent.run("run two scripts"))
    config.unsafe_mode = orig

    # Both tools required confirmation
    assert call_order == ["confirm:run_python", "confirm:run_python"]
