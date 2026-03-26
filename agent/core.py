"""ReAct agent loop: Reason → Act → Observe."""

import copy
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from json import JSONDecodeError, JSONDecoder
from types import SimpleNamespace
from typing import Iterator
from openai.types.chat import ChatCompletionMessageParam

from agent.config import config
from agent.llama_client import get_client
from agent import tools as tool_registry
from agent import memory
from agent.plugins import load_plugins
from agent import stats as _stats
from agent.mode import Mode, parse_mode, get_blocked_tools, get_mode_instruction

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
import agent.tools.ui       # noqa: F401
import agent.tools.think    # noqa: F401

# Load plugins from plugins/ directory
_loaded_plugins = load_plugins()

# Tools that require user confirmation before execution (unless UNSAFE_MODE)
CONFIRM_TOOLS = {"run_shell", "run_background", "write_file", "delete_file", "run_python", "edit_file", "git_commit", "kill_process", "stop_background", "move_file"}

# Maximum number of rewind snapshots to keep in memory
_MAX_SNAPSHOTS = 20

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


def _collect_json_candidates(text: str) -> list[tuple[int, int, object]]:
    """Extract JSON-like payloads embedded in model text.

    Supports valid JSON objects/arrays and a common `{{...}}` wrapper style
    emitted by some local models when trying to "show" a tool call inline.
    """
    decoder = JSONDecoder()
    candidates: list[tuple[int, int, object]] = []
    i = 0

    while i < len(text):
        if text[i] not in "[{":
            i += 1
            continue

        starts = [i]
        if text.startswith("{{", i):
            starts.insert(0, i + 1)

        matched = False
        for start in starts:
            try:
                data, rel_end = decoder.raw_decode(text[start:])
            except JSONDecodeError:
                continue

            end = start + rel_end
            span_start = start
            span_end = end
            if start == i + 1 and text.startswith("{{", i):
                span_start = i
                while span_end < len(text) and text[span_end] == "}":
                    span_end += 1

            candidates.append((span_start, span_end, data))
            i = span_end
            matched = True
            break

        if not matched:
            i += 1

    return candidates


def _build_tool_call(name: str, args: object) -> SimpleNamespace | None:
    """Normalize a parsed tool payload into the internal tool-call shape."""
    if not isinstance(name, str) or not name.strip():
        return None

    normalized_args = args if args not in (None, "") else {}
    if isinstance(normalized_args, str):
        try:
            normalized_args = json.loads(normalized_args)
        except JSONDecodeError:
            pass

    args_str = (
        json.dumps(normalized_args, sort_keys=True)
        if isinstance(normalized_args, (dict, list))
        else str(normalized_args)
    )

    return SimpleNamespace(
        id=f"call_{uuid.uuid4().hex[:8]}",
        function=SimpleNamespace(name=name.strip(), arguments=args_str),
    )


def _tool_calls_from_payload(data: object) -> list[SimpleNamespace]:
    """Decode supported tool-call JSON payloads into internal call objects."""
    if isinstance(data, list):
        calls: list[SimpleNamespace] = []
        for item in data:
            calls.extend(_tool_calls_from_payload(item))
        return calls

    if not isinstance(data, dict):
        return []

    if isinstance(data.get("tool_calls"), list):
        calls: list[SimpleNamespace] = []
        for item in data["tool_calls"]:
            calls.extend(_tool_calls_from_payload(item))
        return calls

    function_obj = data.get("function")
    if isinstance(function_obj, dict):
        name = data.get("name") or function_obj.get("name")
        args = (
            data.get("arguments")
            or data.get("parameters")
            or function_obj.get("arguments")
            or function_obj.get("parameters")
            or {}
        )
        call = _build_tool_call(name, args)
        return [call] if call else []

    name = data.get("name") or data.get("function")
    args = data.get("arguments") or data.get("parameters") or {}
    call = _build_tool_call(name, args)
    return [call] if call else []


def _parse_content_tool_calls(text: str) -> list:
    """
    Try to extract tool call(s) from raw model text.
    Returns a list of SimpleNamespace(id, function) objects, or [].
    """
    payloads: list[object] = []

    for pattern in _XML_PATTERNS:
        for m in pattern.finditer(text):
            raw = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            for _, _, data in _collect_json_candidates(raw):
                payloads.append(data)

    # Also scan the full text for inline JSON-like payloads as a fallback.
    if not payloads:
        for _, _, data in _collect_json_candidates(text):
            payloads.append(data)

    tool_calls = []
    seen: set[tuple] = set()  # deduplicate (name, args) pairs across overlapping patterns

    for data in payloads:
        for tc in _tool_calls_from_payload(data):
            key = (tc.function.name, tc.function.arguments)
            if key in seen:
                continue
            seen.add(key)
            tool_calls.append(tc)

    return tool_calls


def _strip_tool_call_markup(text: str) -> str:
    """Remove tool call markup from model response so only prose is shown."""
    for pattern in _XML_PATTERNS:
        text = pattern.sub("", text)

    spans: list[tuple[int, int]] = []
    for start, end, data in _collect_json_candidates(text):
        if _tool_calls_from_payload(data):
            spans.append((start, end))

    if spans:
        pieces: list[str] = []
        cursor = 0
        for start, end in spans:
            if start > cursor:
                pieces.append(text[cursor:start])
            cursor = max(cursor, end)
        pieces.append(text[cursor:])
        text = "".join(pieces)

    return text.strip()


def _build_system_prompt(context_text: str = "", mode: Mode = Mode.HYBRID) -> str:
    import os
    mem = memory.load_all()
    cwd = os.getcwd()
    parts = [
        "You are a capable local AI assistant with access to tools.",
        f"You are running in the directory: {cwd}",
        "When the user refers to 'this project', 'here', or 'this directory', they mean that working directory.",
        "If the user asks you to create, edit, inspect, search, run, or verify something, use the available tools and do the work instead of describing how you would do it.",
        "Do not emit pseudo-tool examples, placeholder JSON, or markdown snippets that look like tool calls. Actually call the tool.",
        "CRITICAL: When asked to create or modify files, call write_file or edit_file immediately. NEVER show the file contents or code in your response as a substitute — that does not change anything on disk.",
        "Keep visible responses terse. Before tool use, either say nothing or at most one short sentence. When the task is done, give a short final answer.",
        "Available tools let you read/write files, run shell commands, execute Python, and search the web.",
        "DEEP THINKING: Before calling write_file, edit_file, run_shell, run_python, delete_file, or git_commit on a non-trivial task, call the `think` tool first.",
        "In the think call: name every file you will touch, every command you will run, potential side-effects, and anything that could go wrong.",
        "For simple, clearly-scoped actions (e.g. reading a file, a one-liner shell command) you may skip think.",
    ]
    mode_instruction = get_mode_instruction(mode)
    if mode_instruction:
        parts += ["", mode_instruction]
    if mem:
        parts += ["", "## Persistent Memory", mem]
    if context_text:
        parts += ["", "## Project Context", context_text]
    return "\n".join(parts)


class Agent:
    def __init__(
        self,
        confirm_callback=None,
        context_text: str = "",
        load_mcp: bool = True,
        mode: Mode | None = None,
    ):
        """
        Args:
            confirm_callback: callable(tool_name, args) → bool.
                              If None, all confirmations auto-approve (UNSAFE_MODE behaviour).
            context_text: optional extra text injected into system prompt.
            load_mcp: if True, connect to configured external protocol agents on startup.
            mode: execution mode; defaults to config.agent_mode.
        """
        self.client = get_client()
        self.confirm_callback = confirm_callback
        self.history: list[ChatCompletionMessageParam] = []
        self.mode: Mode = mode or parse_mode(config.agent_mode) or Mode.HYBRID

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

        self._context_text = context_text
        self.system_prompt = _build_system_prompt(context_text, self.mode)
        self._snapshots: list[list] = []  # history snapshots for /rewind

    def set_mode(self, mode: Mode) -> None:
        """Switch execution mode and rebuild the system prompt immediately."""
        self.mode = mode
        self.system_prompt = _build_system_prompt(self._context_text, self.mode)

    def reset(self, context_text: str | None = None):
        """Clear conversation history and optionally reload the system prompt.

        Pass *context_text* to replace the project context (e.g. after LLAMA.md
        is created, edited, or deleted).  Omit it to keep the existing prompt.
        """
        self.history = []
        self._snapshots = []
        if context_text is not None:
            self._context_text = context_text
        self.system_prompt = _build_system_prompt(self._context_text, self.mode)

    def _snapshot(self) -> None:
        """Save a deep copy of current history before a new user turn begins.

        Capped at _MAX_SNAPSHOTS entries — oldest snapshots are evicted first
        to bound memory usage on long conversations.
        """
        self._snapshots.append(copy.deepcopy(self.history))
        if len(self._snapshots) > _MAX_SNAPSHOTS:
            self._snapshots = self._snapshots[-_MAX_SNAPSHOTS:]

    def rewind(self, n: int = 1) -> int:
        """Roll back the last *n* user turns.

        Returns the number of turns actually rewound (may be less than *n* if
        fewer snapshots are available — oldest ones are evicted once the cap
        of _MAX_SNAPSHOTS is reached).
        """
        n = min(n, len(self._snapshots))
        if n == 0:
            return 0
        self.history = copy.deepcopy(self._snapshots[-n])
        self._snapshots = self._snapshots[:-n]
        return n

    def get_turns(self) -> list[str]:
        """Return the user messages in current history (most recent last)."""
        return [m["content"] for m in self.history if m.get("role") == "user"]

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
        """Run one user turn.

        Assistant prose is buffered until the model finishes its turn. If that
        turn contains tool calls, the prose is suppressed so the CLI stays
        concise and action-oriented.
        """
        self._maybe_summarize()
        self._snapshot()
        self.history.append({"role": "user", "content": user_input})
        turn_output = ""

        for _ in range(config.max_tool_iterations):
            response_text, tool_calls = self._llm_turn()

            if not tool_calls:
                turn_output += response_text
                if response_text:
                    yield response_text
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

            # Split tool calls into two buckets:
            #  - parallel_safe: no confirmation needed → can run concurrently
            #  - serial: require user confirmation → must run one at a time
            parsed_calls: list[tuple] = []
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                needs_confirm = name in CONFIRM_TOOLS and not config.unsafe_mode
                parsed_calls.append((tc, name, args, needs_confirm))

            # Dispatch all parallel-safe calls concurrently, preserve order.
            parallel_indices = [i for i, (_, _, _, nc) in enumerate(parsed_calls) if not nc]
            observations: dict[int, str] = {}

            if len(parallel_indices) > 1:
                with ThreadPoolExecutor(max_workers=min(len(parallel_indices), 8)) as pool:
                    future_to_idx = {
                        pool.submit(tool_registry.dispatch, parsed_calls[i][1], parsed_calls[i][2]): i
                        for i in parallel_indices
                    }
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            observations[idx] = future.result()
                        except Exception as exc:
                            observations[idx] = f"[tool error: {exc}]"
            elif parallel_indices:
                i = parallel_indices[0]
                try:
                    observations[i] = tool_registry.dispatch(parsed_calls[i][1], parsed_calls[i][2])
                except Exception as exc:
                    observations[i] = f"[tool error: {exc}]"

            # Emit results in original order; handle serial (confirm) calls inline.
            for idx, (tc, name, args, needs_confirm) in enumerate(parsed_calls):
                if needs_confirm:
                    if self.confirm_callback:
                        approved = self.confirm_callback(name, args)
                        observation = tool_registry.dispatch(name, args) if approved else "User declined this action."
                    else:
                        observation = tool_registry.dispatch(name, args)
                else:
                    observation = observations[idx]

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
        """Read one LLM response. Returns (full_text, tool_calls)."""
        tool_calls_acc: dict[int, dict] = {}
        full_text = ""

        blocked = get_blocked_tools(self.mode)
        schemas = [
            s for s in tool_registry.get_all_schemas()
            if s["function"]["name"] not in blocked
        ]
        stream = self.client.chat.completions.create(
            model=config.llama_model,
            messages=self._messages(),
            tools=schemas,
            tool_choice="auto",
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.content:
                full_text += delta.content

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
