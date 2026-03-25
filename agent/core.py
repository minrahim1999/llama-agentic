"""ReAct agent loop: Reason → Act → Observe."""

import json
import re
import uuid
from types import SimpleNamespace
from typing import Iterator
from openai.types.chat import ChatCompletionMessageParam

from agent.config import config
from agent.llama_client import get_client
from agent import tools as tool_registry
from agent import memory
from agent.plugins import load_plugins
from agent import stats as _stats

# Import all built-in tool modules so their @tool decorators fire
import agent.tools.file  # noqa: F401
import agent.tools.shell  # noqa: F401
import agent.tools.code  # noqa: F401
import agent.tools.search  # noqa: F401
import agent.tools.memory  # noqa: F401
import agent.tools.edit  # noqa: F401
import agent.tools.git  # noqa: F401
import agent.tools.web  # noqa: F401
import agent.tools.find  # noqa: F401
import agent.tools.process  # noqa: F401

# Load plugins from plugins/ directory
_loaded_plugins = load_plugins()

# Tools that require user confirmation before execution (unless UNSAFE_MODE)
CONFIRM_TOOLS = {"run_shell", "write_file", "delete_file", "run_python", "edit_file", "git_commit", "kill_process", "move_file"}

# ---------------------------------------------------------------------------
# Content-based tool call parser
# Handles models that emit tool calls as text rather than the tool_calls field.
# Supports Qwen2.5 XML format, hermes-style JSON, and markdown code blocks.
# ---------------------------------------------------------------------------

_XML_PATTERNS = [
    # <functionCalls>...</functionCalls>
    re.compile(r"<functionCalls>\s*(.*?)\s*</functionCalls>", re.DOTALL | re.IGNORECASE),
    # <function_call>...</function_call>  (with or without underscore/space)
    re.compile(r"<function[_ ]?call[s]?>\s*(.*?)\s*</function[_ ]?call[s]?>", re.DOTALL | re.IGNORECASE),
    # ```xml ... ``` code blocks containing JSON
    re.compile(r"```(?:xml|json)?\s*\n?(.*?)\n?```", re.DOTALL),
]


def _parse_content_tool_calls(text: str) -> list:
    """
    Try to extract tool call(s) from raw model text.
    Returns a list of SimpleNamespace(id, function) objects, or [].
    """
    candidates: list[str] = []

    for pattern in _XML_PATTERNS:
        for m in pattern.finditer(text):
            candidates.append(m.group(1).strip())

    # Also try bare JSON objects anywhere in text (last resort)
    if not candidates:
        for m in re.finditer(r'\{[^{}]*"name"\s*:\s*"[^"]+".+?\}', text, re.DOTALL):
            candidates.append(m.group(0))

    tool_calls = []
    seen: set[tuple] = set()  # deduplicate (name, args) pairs across overlapping patterns

    for raw in candidates:
        # Strip any remaining XML tags around the JSON
        raw = re.sub(r"<[^>]+>", "", raw).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if not isinstance(data, dict):
            continue  # skip bare numbers, arrays, etc.

        # Support both {name, arguments} and {name, parameters} keys
        name = data.get("name") or data.get("function")
        args = data.get("arguments") or data.get("parameters") or {}
        if not name:
            continue

        args_str = json.dumps(args, sort_keys=True) if isinstance(args, dict) else str(args)
        key = (name, args_str)
        if key in seen:
            continue
        seen.add(key)

        tc = SimpleNamespace(
            id=f"call_{uuid.uuid4().hex[:8]}",
            function=SimpleNamespace(name=name, arguments=args_str),
        )
        tool_calls.append(tc)

    return tool_calls


def _strip_tool_call_markup(text: str) -> str:
    """Remove tool call markup from model response so only prose is shown."""
    for pattern in _XML_PATTERNS:
        text = pattern.sub("", text)
    # Remove bare JSON tool call blobs
    text = re.sub(r'\{[^{}]*"name"\s*:\s*"[^"]+".+?\}', "", text, flags=re.DOTALL)
    return text.strip()


def _build_system_prompt(context_text: str = "") -> str:
    mem = memory.load_all()
    parts = [
        "You are a capable local AI assistant with access to tools.",
        "Think step by step. Use tools when needed. When the task is done, give a clear final answer.",
        "Available tools let you read/write files, run shell commands, execute Python, and search the web.",
    ]
    if mem:
        parts += ["", "## Persistent Memory", mem]
    if context_text:
        parts += ["", "## Project Context", context_text]
    return "\n".join(parts)


class Agent:
    def __init__(self, confirm_callback=None, context_text: str = "", load_mcp: bool = True):
        """
        Args:
            confirm_callback: callable(tool_name, args) → bool.
                              If None, all confirmations auto-approve (UNSAFE_MODE behaviour).
            context_text: optional extra text injected into system prompt.
            load_mcp: if True, connect to configured external protocol agents on startup.
        """
        self.client = get_client()
        self.confirm_callback = confirm_callback
        self.history: list[ChatCompletionMessageParam] = []

        if load_mcp:
            try:
                from agent.mcp_client import get_manager
                get_manager().load_and_connect(verbose=False)
            except Exception:
                pass  # MCP failures must never break the agent
            try:
                from agent.a2a_client import get_manager as get_a2a_manager
                get_a2a_manager().load_and_connect(verbose=False)
            except Exception:
                pass  # A2A failures must never break the agent

        self.system_prompt = _build_system_prompt(context_text)

    def reset(self):
        self.history = []

    def _windowed_history(self) -> list[ChatCompletionMessageParam]:
        """Return history trimmed to the sliding window.

        Keeps the last `history_window` user turns plus all their associated
        assistant / tool messages. Tool messages are never orphaned — we always
        include the assistant message that triggered them.
        """
        window = config.history_window
        if window <= 0:
            return self.history

        # Walk backwards collecting complete turn groups until we hit the limit
        turns: list[list] = []  # each element = one logical turn (1+ messages)
        i = len(self.history) - 1
        while i >= 0 and len(turns) < window:
            group = []
            # Collect contiguous tool + assistant tail of the turn
            while i >= 0 and self.history[i]["role"] in ("tool", "assistant"):
                group.insert(0, self.history[i])
                i -= 1
            # The user message that started the turn
            if i >= 0 and self.history[i]["role"] == "user":
                group.insert(0, self.history[i])
                i -= 1
            if group:
                turns.insert(0, group)

        flat = [msg for group in turns for msg in group]
        return flat

    def _messages(self) -> list[ChatCompletionMessageParam]:
        return [{"role": "system", "content": self.system_prompt}] + self._windowed_history()

    def _maybe_summarize(self):
        """If history is too long, summarize oldest turns into a single message.

        Triggered when total messages exceed history_window * 3.
        Calls the LLM to produce a "Summary so far" message replacing the oldest half.
        """
        window = config.history_window
        if window <= 0 or len(self.history) <= window * 3:
            return

        # Split: oldest half to summarize, rest to keep
        midpoint = len(self.history) // 2
        to_summarize = self.history[:midpoint]
        to_keep = self.history[midpoint:]

        # Build a summary prompt from the old messages
        convo = "\n".join(
            f"{m['role'].upper()}: {m.get('content') or ''}"
            for m in to_summarize
            if m.get("content")
        )
        summary_messages = [
            {"role": "system", "content": "You are a concise summarizer."},
            {"role": "user", "content": (
                "Summarize the following conversation history in 3-5 bullet points. "
                "Preserve key facts, decisions, file paths, and tool results.\n\n"
                f"{convo}"
            )},
        ]
        try:
            resp = self.client.chat.completions.create(
                model=config.llama_model,
                messages=summary_messages,
                stream=False,
                max_tokens=512,
            )
            summary_text = resp.choices[0].message.content or "(summary unavailable)"
        except Exception:
            return  # summarization failure must never break the agent

        summary_msg: ChatCompletionMessageParam = {
            "role": "assistant",
            "content": f"[Summary of earlier conversation]\n{summary_text}",
        }
        self.history = [summary_msg] + to_keep

    def run(self, user_input: str) -> Iterator[str]:
        """Run one user turn. Yields text chunks as they stream in."""
        self._maybe_summarize()
        self.history.append({"role": "user", "content": user_input})
        turn_output = ""

        for _ in range(config.max_tool_iterations):
            response_text, tool_calls = yield from self._llm_turn()
            turn_output += response_text

            if not tool_calls:
                self.history.append({"role": "assistant", "content": response_text})
                _stats.session_stats.record_turn(user_input, turn_output)
                return

            # Store assistant message (strip XML markup from content before saving)
            clean_text = _strip_tool_call_markup(response_text) or None
            self.history.append({
                "role": "assistant",
                "content": clean_text,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                needs_confirm = name in CONFIRM_TOOLS and not config.unsafe_mode
                if needs_confirm and self.confirm_callback:
                    approved = self.confirm_callback(name, args)
                    observation = tool_registry.dispatch(name, args) if approved else "User declined this action."
                else:
                    observation = tool_registry.dispatch(name, args)

                _stats.session_stats.record_tool_call(observation)
                turn_output += observation
                yield f"\n[tool: {name}]\n{observation}\n"

                self.history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation,
                })

        _stats.session_stats.record_turn(user_input, turn_output)
        yield "\n[max iterations reached]"

    def _llm_turn(self):
        """Stream one LLM response. Returns (full_text, tool_calls)."""
        tool_calls_acc: dict[int, dict] = {}
        full_text = ""

        stream = self.client.chat.completions.create(
            model=config.llama_model,
            messages=self._messages(),
            tools=tool_registry.get_all_schemas(),
            tool_choice="auto",
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.content:
                full_text += delta.content
                yield delta.content

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": tc_delta.id or "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_calls_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_acc[idx]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

        # 1. Proper OpenAI tool_calls from the API
        if tool_calls_acc:
            tool_calls = []
            for idx in sorted(tool_calls_acc):
                d = tool_calls_acc[idx]
                tc = SimpleNamespace(
                    id=d["id"] or f"call_{idx}",
                    function=SimpleNamespace(name=d["name"], arguments=d["arguments"]),
                )
                tool_calls.append(tc)
            return full_text, tool_calls

        # 2. Fallback: parse tool calls embedded in content (Qwen2.5 XML format, etc.)
        content_calls = _parse_content_tool_calls(full_text)
        if content_calls:
            return full_text, content_calls

        return full_text, []
