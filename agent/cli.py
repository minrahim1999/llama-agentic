"""Interactive CLI for the llama-agentic agent."""

from __future__ import annotations

import glob as _glob
import html as _html
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

import click
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import CompleteEvent, Completer, Completion
    from prompt_toolkit.formatted_text import ANSI, HTML
    from prompt_toolkit.history import InMemoryHistory
    _PROMPT_TOOLKIT_AVAILABLE = True
except ModuleNotFoundError:
    PromptSession = None
    CompleteEvent = object
    ANSI = str
    HTML = str
    InMemoryHistory = None
    _PROMPT_TOOLKIT_AVAILABLE = False

    class Completer:  # type: ignore[no-redef]
        """Fallback stub when prompt_toolkit is unavailable."""

    class Completion:  # type: ignore[no-redef]
        """Fallback stub when prompt_toolkit is unavailable."""

        def __init__(self, text: str, start_position: int = 0, display=None, display_meta=None):
            self.text = text
            self.start_position = start_position
            self.display = display
            self.display_meta = display_meta
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from agent import __version__
from agent.config import config, is_first_run, use_project_data_dirs
from agent.core import Agent
from agent import memory, session
from agent.server_manager import ensure_server
from agent.tools.edit import compute_diff
from agent.init_cmd import load_llama_md

console = Console()


def _clear_screen() -> None:
    """Clear the terminal screen and scrollback buffer cross-platform.

    - Windows: runs ``cls`` via the shell.
    - macOS / Linux: writes ANSI sequences directly so no subprocess is needed.
      ``\\033[3J`` clears the scrollback buffer (supported by most modern
      terminals including iTerm2, Terminal.app, GNOME Terminal, Alacritty).
      ``\\033[H\\033[2J`` moves the cursor to the top and clears the visible area.
      Falls back to ``subprocess(['clear'])`` if stdout is not a real tty
      (e.g. piped output) so the sequences won't garble logs.
    """
    if sys.platform == "win32":
        os.system("cls")
    else:
        if sys.stdout.isatty():
            # Clear scrollback + visible area without spawning a subprocess
            sys.stdout.write("\033[3J\033[H\033[2J")
            sys.stdout.flush()
        else:
            # Fallback for non-tty (piped/redirected)
            subprocess.run(["clear"], check=False)


_CONTEXT_READ_FILES = {"CLAUDE.md", "README.md", "README", "pyproject.toml", "package.json"}
_CONTEXT_FILE_LIMIT = 2000
_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".claude", ".llama-agentic"}

# Show full tool output (toggled by /verbose)
_verbose_tools: bool = False
_ACCENT = "#d08770"
_PROMPT = "#a7b1c2"
_PROJECT = "#88c0d0"
_HINT = "#b48ead"
_MUTED = "#a0a0a0"


@dataclass(frozen=True)
class SlashCommandSpec:
    name: str
    usage: str
    description: str


_SLASH_COMMAND_SPECS: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec("help", "/help", "Show available slash commands"),
    SlashCommandSpec("init", "/init [--force]", "Generate LLAMA.md for this project"),
    SlashCommandSpec("refresh", "/refresh", "Re-generate LLAMA.md from current project state"),
    SlashCommandSpec("add", "/add <glob>", "Attach file(s) to the current chat context"),
    SlashCommandSpec("undo", "/undo <file>", "Restore the last .bak version of a file"),
    SlashCommandSpec("model", "/model [name]", "Show or switch the active model"),
    SlashCommandSpec("tools", "/tools", "List all registered tools"),
    SlashCommandSpec("tool", "/tool <name>", "Show one tool's description and input schema"),
    SlashCommandSpec("mode", "/mode [name|save]", "Show or switch the agent mode (chat/plan/code/hybrid/review)"),
    SlashCommandSpec("bg", "/bg", "List background processes and their recent output"),
    SlashCommandSpec("clear", "/clear", "Clear the terminal screen (keeps conversation history)"),
    SlashCommandSpec("rewind", "/rewind [n]", "Undo the last n turns (default 1)"),
    SlashCommandSpec("reset", "/reset", "Clear conversation history and start a new session"),
    SlashCommandSpec("save", "/save [name]", "Save the current session"),
    SlashCommandSpec("load", "/load <name>", "Load a saved session"),
    SlashCommandSpec("sessions", "/sessions", "List saved sessions"),
    SlashCommandSpec("memory", "/memory", "List persistent memory keys"),
    SlashCommandSpec("forget", "/forget <key>", "Delete a memory entry"),
    SlashCommandSpec("history", "/history", "Show history window stats"),
    SlashCommandSpec("verbose", "/verbose", "Toggle full tool output"),
    SlashCommandSpec("cost", "/cost", "Show session token and tool-call stats"),
    SlashCommandSpec("trust", "/trust [revoke <key>]", "List or revoke saved trust entries"),
    SlashCommandSpec("exit", "/exit", "Quit the REPL"),
)

# Maps command name → group label shown in the completion menu
_SLASH_COMMAND_GROUP: dict[str, str] = {
    "trust": "config",
    "help": "utility",
    "init": "project",
    "refresh": "project",
    "add": "context",
    "undo": "context",
    "model": "config",
    "tools": "utility",
    "tool": "utility",
    "reset": "session",
    "save": "session",
    "load": "session",
    "sessions": "session",
    "memory": "memory",
    "forget": "memory",
    "history": "session",
    "verbose": "config",
    "cost": "session",
    "exit": "utility",
}


# ── Confirmation ──────────────────────────────────────────────────────────────

def _confirm_panel(name: str, args: dict) -> None:
    """Render a human-readable confirmation panel for a tool call."""

    def _kv(label: str, value: str) -> Text:
        t = Text()
        t.append(f"{label}: ", style="dim")
        t.append(value, style="bold")
        return t

    if name == "run_shell":
        cmd     = args.get("command", "")
        cwd     = args.get("cwd") or "."
        timeout = args.get("timeout", 30)
        meta = Text()
        meta.append("  cwd: ", style="dim")
        meta.append(str(cwd), style="bold cyan")
        meta.append("    timeout: ", style="dim")
        meta.append(f"{timeout}s", style="bold cyan")
        body = Group(
            Syntax(cmd, "bash", theme="monokai", word_wrap=True, background_color="default"),
            Rule(style="dim white"),
            meta,
        )
        console.print(Panel(
            body,
            title=Text.assemble(("  $ ", "bold bright_green"), ("run_shell", "bold bright_green")),
            title_align="left",
            border_style="bright_green",
            padding=(1, 2),
        ))

    elif name == "run_background":
        cmd     = args.get("command", "")
        cwd     = args.get("cwd") or "."
        port    = args.get("port") or ""
        meta = Text()
        meta.append("  cwd: ", style="dim")
        meta.append(str(cwd), style="bold cyan")
        if port:
            meta.append("    port: ", style="dim")
            meta.append(str(port), style="bold cyan")
        body = Group(
            Syntax(cmd, "bash", theme="monokai", word_wrap=True, background_color="default"),
            Rule(style="dim white"),
            meta,
        )
        console.print(Panel(
            body,
            title=Text.assemble(("  ⬡ ", "bold bright_cyan"), ("run_background", "bold bright_cyan")),
            title_align="left",
            border_style="bright_cyan",
            padding=(1, 2),
        ))

    elif name == "run_python":
        code = args.get("code", "")
        console.print(Panel(
            Syntax(code, "python", theme="monokai", word_wrap=True),
            title=Text.assemble((" ", ""), ("run_python", "bold yellow")),
            title_align="left", border_style="yellow", padding=(0, 1)))

    elif name == "write_file":
        path    = args.get("path", "")
        content = args.get("content", "")
        lines   = content.count("\n") + 1
        console.print(Panel(
            Syntax(content[:2000], _lang_for(path), theme="nord", word_wrap=True),
            title=Text.assemble((" ", ""), ("write_file", "bold yellow"), (f"  {path}", "white")),
            title_align="left", border_style="yellow",
            subtitle=f"[dim]{lines} lines[/dim]", subtitle_align="right",
            padding=(0, 1)))

    elif name == "edit_file":
        path      = args.get("path", "")
        diff_text = compute_diff(path, args.get("old_string", ""), args.get("new_string", ""))
        console.print(Panel(
            Syntax(diff_text, "diff", theme="monokai", word_wrap=True),
            title=Text.assemble((" ", ""), ("edit_file", "bold yellow"), (f"  {path}", "white")),
            title_align="left", border_style="yellow", padding=(0, 1)))

    elif name == "delete_file":
        path = args.get("path", "")
        console.print(Panel(
            Text(f"  {path}", style="bold red"),
            title=Text.assemble((" ", ""), ("delete_file", "bold red")),
            title_align="left", border_style="red", padding=(0, 1)))

    elif name == "git_commit":
        msg   = args.get("message", "")
        files = args.get("files") or []
        body  = Group(
            Text(msg, style="bold"),
            *(Text(f"  {f}", style="dim") for f in files),
        )
        console.print(Panel(body,
            title=Text.assemble((" ", ""), ("git_commit", "bold yellow")),
            title_align="left", border_style="yellow", padding=(0, 2)))

    elif name == "move_file":
        src = args.get("src", "")
        dst = args.get("dst", "")
        console.print(Panel(
            Text(f"{src}  →  {dst}", style="bold"),
            title=Text.assemble((" ", ""), ("move_file", "bold yellow")),
            title_align="left", border_style="yellow", padding=(0, 2)))

    elif name in ("ask_choice", "ask_questions"):
        # These tools are interactive by design — no extra panel needed;
        # the prompt_ui selector is the UI. Just show a slim header.
        question = args.get("question", args.get("questions_json", ""))[:120]
        is_multi = args.get("multi", False)
        tag = "multi-select" if is_multi else "single-select"
        console.print(Panel(
            Text(question, style=_MUTED),
            title=Text.assemble(("  ⬡ ", f"bold {_HINT}"), (name, f"bold {_HINT}"), (f"  {tag}", _MUTED)),
            title_align="left", border_style=_HINT, padding=(0, 2)))

    else:
        # Generic fallback: clean key/value layout instead of raw JSON
        rows = "\n".join(f"  [dim]{k}:[/dim] {v}" for k, v in args.items())
        console.print(Panel(
            rows or "[dim](no arguments)[/dim]",
            title=Text.assemble((" ", ""), (name, "bold yellow")),
            title_align="left", border_style="yellow", padding=(0, 1)))


def _pick(prompt: str, choices: "list[tuple[str, str]]") -> int:
    """Render a numbered choice list and return the 0-based index chosen.

    *choices* is a list of (label, description) pairs.
    """
    console.print()
    for i, (label, desc) in enumerate(choices, 1):
        num  = Text(f"  {i}  ", style=f"bold {_ACCENT}")
        lbl  = Text(f"{label}", style="bold white")
        dsc  = Text(f"  {desc}", style=_MUTED) if desc else Text("")
        line = Text.assemble(num, lbl, dsc)
        console.print(line)
    console.print()

    valid = {str(i) for i in range(1, len(choices) + 1)}
    while True:
        raw = console.input(f"  {prompt} › ").strip()
        if raw in valid:
            return int(raw) - 1
        console.print(f"  [dim]Enter a number from 1 to {len(choices)}.[/dim]")


def _ask_project_trust() -> None:
    """One-time dialog: offer to grant blanket trust for this project."""
    from agent.trust import mark_asked, remember_all

    console.print()
    console.print(
        Panel(
            Group(
                Text.assemble(
                    ("llama-agent ", f"bold {_ACCENT}"),
                    ("wants to run tools in this project.", "white"),
                ),
                Text(""),
                Text(
                    "You can grant it full access now to skip approval prompts in future,\n"
                    "or choose to review each action individually.",
                    style=_MUTED,
                ),
            ),
            title=Text.assemble(("  Grant full access?", f"bold {_ACCENT}")),
            title_align="left",
            border_style=_ACCENT,
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )

    idx = _pick("Choose", [
        ("Yes, for this project", "saved to .llama-agentic/trust.json — won't ask again here"),
        ("Yes, always",           "saved globally — won't ask again anywhere"),
        ("No, ask me each time",  "you'll approve each action individually"),
    ])

    if idx == 0:
        remember_all("project")
        console.print("  [dim]Full access granted for this project.[/dim]\n")
    elif idx == 1:
        remember_all("global")
        console.print("  [dim]Full access granted globally.[/dim]\n")
    else:
        mark_asked()  # mark as asked so we don't show this dialog again
        console.print("  [dim]Got it — will ask for each action.[/dim]\n")


def _confirm_tool(name: str, args: dict) -> bool:
    """Show confirmation UI for a tool call. Respects trust store."""
    from agent.trust import is_trusted, full_access_asked, remember

    # Blanket or per-tool trust → auto-approve
    if is_trusted(name, args):
        return True

    # First time any confirmation is needed → offer full-access grant
    if not full_access_asked():
        _ask_project_trust()
        # Re-check: user may have granted blanket trust just now
        if is_trusted(name, args):
            return True

    # Per-action confirmation
    _confirm_panel(name, args)

    idx = _pick("Allow this action?", [
        ("Yes, just this once",      ""),
        ("Yes, for this project",    "won't ask again in this project"),
        ("Yes, always",              "won't ask again anywhere"),
        ("No, skip this action",     ""),
    ])

    if idx == 0:
        return True
    if idx == 1:
        remember(name, args, "project")
        console.print("  [dim]Remembered for this project.[/dim]")
        return True
    if idx == 2:
        remember(name, args, "global")
        console.print("  [dim]Remembered globally.[/dim]")
        return True
    # idx == 3 → No
    return False


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(context_dir: str | None) -> str:
    root = Path(context_dir).resolve() if context_dir else None
    if root is None or not root.exists():
        return ""

    sections: list[str] = [f"# Project: {root.name}", f"Path: {root}"]
    for fname in _CONTEXT_READ_FILES:
        fpath = root / fname
        if fpath.exists() and fpath.is_file():
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            if len(text) > _CONTEXT_FILE_LIMIT:
                text = text[:_CONTEXT_FILE_LIMIT] + f"\n... ({len(text)} chars, truncated)"
            sections.append(f"\n## {fname}\n{text}")

    tree_lines: list[str] = []
    for entry in sorted(root.rglob("*")):
        if any(part in _SKIP_DIRS for part in entry.parts):
            continue
        rel = entry.relative_to(root)
        depth = len(rel.parts) - 1
        icon = "📄 " if entry.is_file() else "📁 "
        tree_lines.append("  " * depth + icon + entry.name)
        if len(tree_lines) >= 80:
            tree_lines.append("  ... (truncated)")
            break
    if tree_lines:
        sections.append("\n## File tree\n" + "\n".join(tree_lines))

    return "\n".join(sections)


# ── Chat UI helpers ───────────────────────────────────────────────────────────

def _print_user_message(text: str):
    """Render a compact user message line for non-interactive flows."""
    console.print()
    console.print(f"[bold {_PROMPT}]>[/bold {_PROMPT}] {text}")


def _format_recent_activity() -> str:
    """Summarize the most recent saved session for the dashboard."""
    recent = session.list_sessions()[:1]
    if not recent:
        return "No recent activity"

    path = Path(config.sessions_dir) / recent[0]
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%b %d %H:%M")
    except FileNotFoundError:
        return "No recent activity"

    stem = path.stem
    label = stem.rsplit("_", 2)[0] if "_" in stem else stem
    return f"{label} updated {modified}"


def _compact_label(value: str, limit: int = 36) -> str:
    """Trim long labels for narrow header regions."""
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _command_specs() -> tuple[SlashCommandSpec, ...]:
    """Return the supported interactive slash commands."""
    return _SLASH_COMMAND_SPECS


def _tool_specs() -> list[tuple[str, str]]:
    """Return registered tool names with descriptions."""
    from agent import tools as tr

    specs: list[tuple[str, str]] = []
    for name in sorted(tr._REGISTRY.keys()):
        desc = tr._REGISTRY[name]["schema"]["function"]["description"]
        specs.append((name, desc))
    return specs


def _match_slash_suggestions(text: str) -> list[tuple[str, str]]:
    """Return slash-command suggestions for the current input buffer."""
    if not text.startswith("/"):
        return []

    if text.startswith("/tool "):
        prefix = text[6:].strip().lower()
        matches: list[tuple[str, str]] = []
        for name, desc in _tool_specs():
            if not prefix or name.lower().startswith(prefix):
                matches.append((f"/tool {name}", f"tool · {desc}"))
        return matches

    prefix = text[1:].lower()
    matches = []
    for spec in _command_specs():
        if not prefix or spec.name.startswith(prefix):
            matches.append((spec.usage, spec.description))
    return matches


class SlashCommandCompleter(Completer):
    """Prompt toolkit completer for slash command discovery.

    Displays a formatted popup listing all commands (grouped) when the user
    types "/" alone, or narrows to matching commands as they keep typing.
    """

    def get_completions(self, document, complete_event: CompleteEvent):
        if not _PROMPT_TOOLKIT_AVAILABLE:
            return
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        if text.startswith("/tool "):
            # Sub-complete tool names after /tool <prefix>
            prefix = text[6:].strip().lower()
            for name, desc in _tool_specs():
                if not prefix or name.lower().startswith(prefix):
                    display = HTML(f"<b>/tool {_html.escape(name)}</b>")
                    display_meta = HTML(f"<ansiblue>tool</ansiblue>  {_html.escape(desc[:60])}")
                    yield Completion(
                        f"/tool {name}",
                        start_position=-len(text),
                        display=display,
                        display_meta=display_meta,
                    )
            return

        prefix = text[1:].lower()
        for spec in _command_specs():
            if not prefix or spec.name.startswith(prefix):
                group = _SLASH_COMMAND_GROUP.get(spec.name, "")
                display = HTML(f"<b>{_html.escape(spec.usage)}</b>")
                display_meta = HTML(
                    f"<ansiyellow>{_html.escape(group)}</ansiyellow>  {_html.escape(spec.description)}"
                )
                yield Completion(
                    spec.usage.split()[0],  # complete to just the command word
                    start_position=-len(text),
                    display=display,
                    display_meta=display_meta,
                )


def _toolbar_message() -> ANSI:
    """Bottom toolbar for the interactive prompt."""
    if not _PROMPT_TOOLKIT_AVAILABLE:
        return ""
    return ANSI(
        "\x1b[38;5;141m/\x1b[0m"
        "\x1b[38;5;244m list commands  \x1b[0m"
        "\x1b[38;5;183mTab\x1b[0m"
        "\x1b[38;5;244m complete  \x1b[0m"
        "\x1b[38;5;183m↑↓\x1b[0m"
        "\x1b[38;5;244m history  \x1b[0m"
        "\x1b[38;5;183mEnter\x1b[0m"
        "\x1b[38;5;244m submit  \x1b[0m"
        "\x1b[38;5;183mAlt+Enter\x1b[0m"
        "\x1b[38;5;244m newline\x1b[0m"
    )


def _build_prompt_session():
    """Create the interactive prompt session with slash completion enabled.

    Multiline mode is enabled so that pasted content containing newlines is
    accepted as a single message rather than being submitted line-by-line.
    Key bindings:
      Enter       — submit the current buffer (same UX as a normal single-line prompt)
      Alt+Enter   — insert a literal newline (for manually composing multi-line input)
    """
    if not _PROMPT_TOOLKIT_AVAILABLE or PromptSession is None or InMemoryHistory is None:
        return None

    # Build a themed style if prompt_toolkit.styles is available
    style = None
    try:
        from prompt_toolkit.styles import Style as PTStyle
        style = PTStyle.from_dict({
            "completion-menu": "bg:#1e2030 #c0caf5",
            "completion-menu.completion": "bg:#1e2030 #c0caf5",
            "completion-menu.completion.current": "bg:#3d59a1 #ffffff bold",
            "completion-menu.meta.completion": "bg:#16161e #565f89",
            "completion-menu.meta.completion.current": "bg:#3d59a1 #a9b1d6",
            "bottom-toolbar": "bg:#16161e #565f89",
        })
    except Exception:
        pass

    # Key bindings: Enter submits; Alt+Enter inserts a newline.
    kb = None
    try:
        from prompt_toolkit.key_binding import KeyBindings as _KB
        kb = _KB()

        @kb.add("enter")
        def _submit(event):
            event.current_buffer.validate_and_handle()

        @kb.add("escape", "enter")   # Alt+Enter
        def _newline(event):
            event.current_buffer.insert_text("\n")
    except Exception:
        kb = None

    kwargs: dict = dict(
        completer=SlashCommandCompleter(),
        complete_while_typing=True,
        complete_in_thread=False,  # instant response for "/" popup
        reserve_space_for_menu=10,
        history=InMemoryHistory(),
        bottom_toolbar=_toolbar_message,
        multiline=True,             # accept pasted newlines as part of the message
    )
    if style is not None:
        kwargs["style"] = style
    if kb is not None:
        kwargs["key_bindings"] = kb
    return PromptSession(**kwargs)


def _dashboard_panel(
    cwd: Path,
    tips: list[str],
    quick_actions: list[str],
    has_llama_md: bool = False,
    has_mcp: bool = False,
    has_a2a: bool = False,
    agent_mode=None,
) -> Panel:
    """Render the startup dashboard panel."""
    from agent.mode import Mode as _Mode, mode_label as _ml, mode_colour as _mc
    _mode = agent_mode if agent_mode is not None else _Mode.HYBRID
    _mcol = _mc(_mode)

    # ── Status pills ──────────────────────────────────────────────────────────
    status_row = Text()
    status_row.append("  llama-server ", style=f"bold {_ACCENT}")
    status_row.append("running", style="bold bright_green")
    status_row.append("  mode ", style=f"  bold {_ACCENT}")
    status_row.append(_ml(_mode), style=f"bold {_mcol}")
    if has_llama_md:
        status_row.append("  LLAMA.md ", style=f"  bold {_ACCENT}")
        status_row.append("loaded", style="bold bright_green")
    if has_mcp:
        status_row.append("  MCP ", style=f"  bold {_ACCENT}")
        status_row.append("connected", style="bold bright_green")
    if has_a2a:
        status_row.append("  A2A ", style=f"  bold {_ACCENT}")
        status_row.append("connected", style="bold bright_green")

    left = Group(
        Text.from_markup("[bold]Welcome back![/bold]"),
        Text(""),
        Text("        ▄▄▄        ", style=_ACCENT),
        Text("      ▄█████▄      ", style=_ACCENT),
        Text("      █ ▄ ▄ █      ", style=_ACCENT),
        Text("      ███████      ", style=_ACCENT),
        Text("       ▀█ █▀       ", style=_ACCENT),
        Text(""),
        Text.from_markup(
            f"[bold]{_compact_label(config.llama_model, 52)}[/bold]"
            f" [dim]llama-agentic v{__version__}[/dim]"
        ),
        Text(str(cwd), style=_MUTED),
        Text(""),
        status_row,
    )

    def _bullet(text: str, style: str = _MUTED) -> Text:
        t = Text()
        t.append("  • ", style=_ACCENT)
        t.append(text, style=style)
        return t

    right = Group(
        Text("Tips for getting started", style=f"bold {_ACCENT}"),
        *[_bullet(tip) for tip in tips],
        Text(""),
        Text("Recent activity", style=f"bold {_ACCENT}"),
        _bullet(_format_recent_activity()),
        Text(""),
        Text("Quick actions", style=f"bold {_ACCENT}"),
        *[_bullet(action) for action in quick_actions],
    )

    split = Table.grid(expand=True)
    split.add_column(ratio=5)
    split.add_column(width=3)
    split.add_column(ratio=6)
    split.add_row(left, Text("│", style=_ACCENT), right)

    return Panel(
        split,
        title=f"[{_ACCENT}]Llama Agentic v{__version__}[/{_ACCENT}]",
        title_align="left",
        border_style=_ACCENT,
        box=box.ROUNDED,
        padding=(0, 1),
        expand=False,
    )


def _print_banner(cwd: Path, project_name: str, model_label: str, has_llama_md: bool, has_mcp: bool, has_a2a: bool, agent_mode=None):
    """Render the startup dashboard."""
    tips = [
        "Run /init to generate a LLAMA.md context file for this project",
        "/help shows all commands  ·  /verbose toggles full tool output",
    ]
    if has_mcp or has_a2a:
        connectors = []
        if has_mcp:
            connectors.append("MCP")
        if has_a2a:
            connectors.append("A2A")
        tips.append(f"External integrations active: {', '.join(connectors)}")

    quick_actions = [
        (
            f"Type / to browse {len(_tool_specs())} tools and commands"
            if _PROMPT_TOOLKIT_AVAILABLE
            else "Run /help to list available commands"
        ),
        "/tool <name> — inspect a tool's schema and description",
        "/history or /cost — session stats and token usage",
        "/save [name] — save session  ·  /load <name> — restore",
    ]

    console.print()
    console.print(_dashboard_panel(cwd, tips, quick_actions, has_llama_md, has_mcp, has_a2a, agent_mode=agent_mode))
    console.print(Rule(style="grey35"))
    # Keybindings hint bar
    console.print(
        Text.assemble(
            ("  /", "bold " + _ACCENT),
            (" commands", _MUTED),
            ("   Tab", "bold " + _HINT),
            (" complete", _MUTED),
            ("   ↑↓", "bold " + _HINT),
            (" history", _MUTED),
            ("   Enter", "bold " + _HINT),
            (" submit", _MUTED),
            ("   /exit", "bold " + _ACCENT),
            (" quit", _MUTED),
        )
    )


def _tool_status(chunk: str) -> tuple[str, str]:
    """Parse '\n[tool: name]\nfull_output\n' → (name, full_output)."""
    lines = chunk.strip().split("\n", 1)  # header + ALL output
    header = lines[0]
    name = header.replace("[tool:", "").replace("]", "").strip()
    output = lines[1] if len(lines) > 1 else ""
    return name, output


# ── File-action panel helpers ─────────────────────────────────────────────────

_FILE_PREVIEW_TOOLS = {"write_file", "edit_file"}
_FILE_ACTION_TOOLS  = {"make_dir", "copy_file", "move_file", "delete_file"}

_EXT_LANG: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".json": "json",
    ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".sh": "bash", ".html": "html",
    ".css": "css", ".sql": "sql", ".rs": "rust",
    ".go": "go", ".java": "java", ".c": "c", ".cpp": "cpp",
}


def _lang_for(path: str) -> str:
    return _EXT_LANG.get(Path(path).suffix.lower(), "text")


def _file_preview_panel(path: str, label: str) -> None:
    """Render the contents of *path* in a blue preview panel."""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    lines = content.count("\n") + 1
    console.print(Panel(
        Syntax(content, _lang_for(path), theme="nord", word_wrap=True, line_numbers=False),
        title=Text.assemble((" ", ""), (Path(path).name, "bold white"), (f"  {label}", "dim")),
        title_align="left",
        border_style="blue",
        subtitle=f"[dim]{lines} lines · {len(content)} chars[/dim]",
        subtitle_align="right",
        padding=(0, 1),
    ))


def _render_file_tool(name: str, output: str) -> bool:
    """Render a file-operation result as a panel.

    Returns True when handled (caller skips default one-liner).
    """
    s = output.strip()

    if name == "write_file":
        # "Written N characters to <path>"
        if s.startswith("Written ") and " to " in s:
            path = s.split(" to ", 1)[1].strip()
            console.print()
            _file_preview_panel(path, "written")
            return True

    if name == "edit_file":
        if s.startswith("Created: "):
            path = s.split("Created: ", 1)[1].split(" (")[0].strip()
            console.print()
            _file_preview_panel(path, "created")
            return True
        if s.startswith("Edited: "):
            lines = s.split("\n", 1)
            path = lines[0].replace("Edited: ", "").strip()
            diff_text = lines[1].strip() if len(lines) > 1 else ""
            console.print()
            if diff_text and diff_text != "(no visible diff)":
                console.print(Panel(
                    Syntax(diff_text, "diff", theme="monokai", word_wrap=True),
                    title=Text.assemble((" ", ""), (Path(path).name, "bold white"), ("  modified", "dim")),
                    title_align="left",
                    border_style="blue",
                    padding=(0, 1),
                ))
            else:
                console.print(f"[dim]edit_file[/dim]  [green]✓[/green]  [dim]{path} (no diff)[/dim]")
            return True

    if name == "make_dir":
        path = s.replace("Directory created:", "").strip()
        console.print()
        console.print(Panel(
            Text(f"  {path}", style="bold"),
            title=Text(" folder created", style="dim"),
            title_align="left",
            border_style="blue",
            padding=(0, 1),
        ))
        return True

    if name in ("copy_file", "move_file"):
        icon = "copy" if name == "copy_file" else "moved"
        console.print()
        console.print(Panel(
            Text(f"  {s}", style="dim"),
            title=Text(f" {icon}", style="dim"),
            title_align="left",
            border_style="blue",
            padding=(0, 1),
        ))
        return True

    if name == "delete_file":
        path = s.replace("Deleted:", "").strip()
        console.print()
        console.print(Panel(
            Text(f"  {path}", style="dim red"),
            title=Text(" deleted", style="dim red"),
            title_align="left",
            border_style="red",
            padding=(0, 1),
        ))
        return True

    return False


# ── Agent runner ──────────────────────────────────────────────────────────────

def _run_turn(agent: Agent, user_input: str, show_bubble: bool = True):
    from agent.stats import session_stats
    global _verbose_tools

    if show_bubble:
        _print_user_message(user_input)

    gen = agent.run(user_input)
    tool_calls_this_turn: list[str] = []
    saw_output = False

    # Line-buffered streaming state for code-block detection
    line_buf = ""
    in_code_block = False
    code_lang = ""
    code_buf = ""

    def _flush_code_block():
        nonlocal in_code_block, code_lang, code_buf
        lang = code_lang or "text"
        if code_buf.strip():
            console.print(
                Syntax(code_buf.rstrip("\n"), lang, theme="monokai",
                       background_color="default", word_wrap=True)
            )
        in_code_block = False
        code_lang = ""
        code_buf = ""

    import re as _re  # local import, used by both helpers below

    def _md_to_rich(text: str) -> str:
        """Convert inline markdown to Rich markup. Escapes existing brackets first."""
        # Escape any existing Rich markup chars to prevent injection
        out = text.replace("[", r"\[")
        # bold+italic ***text***
        out = _re.sub(r"\*\*\*(.+?)\*\*\*", r"[bold italic]\1[/bold italic]", out)
        # bold **text**
        out = _re.sub(r"\*\*(.+?)\*\*", r"[bold]\1[/bold]", out)
        # italic *text* or _text_  (single word boundary, avoid false positives)
        out = _re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"[italic]\1[/italic]", out)
        out = _re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"[italic]\1[/italic]", out)
        # inline `code`
        out = _re.sub(r"`([^`]+)`", r"[bold cyan]\1[/bold cyan]", out)
        return out

    def _print_text_line(line: str):
        nonlocal in_code_block, code_lang, code_buf
        stripped = line.rstrip()
        if stripped.startswith("```"):
            if in_code_block:
                _flush_code_block()
            else:
                in_code_block = True
                code_lang = stripped[3:].strip()
        elif in_code_block:
            code_buf += line + "\n"
        elif stripped.startswith("#"):
            # H1/H2/H3 → increasingly smaller bold styles
            level = len(stripped) - len(stripped.lstrip("#"))
            content = stripped.lstrip("#").strip()
            style = "bold cyan" if level == 1 else "bold" if level == 2 else "bold dim"
            console.print(_md_to_rich(content), style=style)
        elif stripped.startswith(("- ", "* ", "+ ")):
            # Unordered list item
            content = stripped[2:]
            console.print(f"  [dim]•[/dim] {_md_to_rich(content)}")
        elif _re.match(r"^\d+\.\s", stripped):
            # Numbered list: "1. foo"
            m = _re.match(r"^(\d+)\.\s+(.*)", stripped)
            if m:
                console.print(f"  [bold cyan]{m.group(1)}.[/bold cyan] {_md_to_rich(m.group(2))}")
        elif stripped.startswith("> "):
            # Blockquote
            console.print(f"  [dim]│[/dim] [dim]{_md_to_rich(stripped[2:])}[/dim]")
        else:
            console.print(_md_to_rich(line) if line.strip() else "")

    try:
        while True:
            chunk = next(gen)
            if chunk.startswith("\n[tool:"):
                saw_output = True
                # Flush partial line buffer before tool status
                if line_buf:
                    if in_code_block:
                        code_buf += line_buf
                    else:
                        console.print(line_buf, end="", markup=False)
                    line_buf = ""

                name, output = _tool_status(chunk)
                tool_calls_this_turn.append(name)
                output_stripped = output.strip()
                is_error = output_stripped.startswith("Error:") or "declined" in output_stripped.lower()
                brief = output_stripped.split("\n")[0][:100] if output_stripped else ""

                if name == "think":
                    # Render the model's reasoning as a distinct thought panel.
                    console.print()
                    console.print(Panel(
                        output_stripped or "(empty)",
                        title="[bold #b48ead]● thinking[/bold #b48ead]",
                        title_align="left",
                        border_style="#b48ead dim",
                        padding=(0, 1),
                    ))
                elif is_error:
                    console.print()
                    console.print(
                        f"[red]x[/red] [bold]{name}[/bold]"
                        + (f"  [dim]{brief}[/dim]" if brief else "")
                    )
                elif _render_file_tool(name, output):
                    pass  # panel already printed
                else:
                    console.print()
                    line = f"[dim]{name}[/dim]  [green]✓[/green]"
                    if brief:
                        line += f"  [dim]{brief}[/dim]"
                    console.print(line)
                    if _verbose_tools and output_stripped:
                        console.print(
                            Panel(output_stripped, border_style="dim", padding=(0, 1)),
                            style="dim",
                        )
            else:
                if chunk.strip():
                    saw_output = True
                # Line-buffered processing for code-block detection & coloring
                line_buf += chunk
                while "\n" in line_buf:
                    text_line, line_buf = line_buf.split("\n", 1)
                    _print_text_line(text_line)
    except StopIteration:
        pass

    # Flush any remaining buffered content
    if line_buf:
        if in_code_block:
            code_buf += line_buf
        else:
            console.print(line_buf, end="", markup=False)

    if saw_output:
        console.print()
    tool_summary = (
        f"{len(tool_calls_this_turn)} tool{'s' if len(tool_calls_this_turn) != 1 else ''}: "
        + ", ".join(tool_calls_this_turn)
        if tool_calls_this_turn
        else "0 tools"
    )
    console.print(
        f"[dim]~{session_stats.estimated_tokens:,} tokens · {tool_summary} · turn {session_stats.turns}[/dim]"
    )


# ── Help ──────────────────────────────────────────────────────────────────────

def _show_help():
    table = Table(show_header=False, box=None, padding=(0, 2))
    for spec in _command_specs():
        table.add_row(f"[bold]{spec.usage}[/bold]", spec.description)
    console.print(Panel(table, title="[bold]Commands[/bold]", border_style="dim"))


def _show_tools():
    """Render a table of all registered tools."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    for name, desc in _tool_specs():
        table.add_row(f"[bold]{name}[/bold]", f"[dim]{desc}[/dim]")
    console.print(Panel(table, title=f"[bold]Tools ({len(_tool_specs())})[/bold]", border_style="dim"))


def _show_tool_detail(tool_name: str):
    """Render details for a single tool."""
    from agent import tools as tr

    if tool_name not in tr._REGISTRY:
        console.print(f"[yellow]Unknown tool:[/yellow] {tool_name}")
        return

    schema = tr._REGISTRY[tool_name]["schema"]["function"]
    params = json.dumps(schema["parameters"], indent=2)
    body = Group(
        Text(schema["description"] or "(no description)", style=_MUTED),
        Text(""),
        Syntax(params, "json", theme="monokai", word_wrap=True, line_numbers=False),
    )
    console.print(Panel(body, title=f"[bold]{tool_name}[/bold]", border_style="dim"))


def _ansi_prompt_text(mode_code: int = 173) -> ANSI:
    """Prompt text for the interactive session, coloured by current mode."""
    return ANSI(f"\n\x1b[38;5;{mode_code}m› \x1b[0m")


def _read_repl_input(prompt_session: "PromptSession[str] | None", mode_code: int = 173) -> str:
    """Read one line from the interactive prompt."""
    if prompt_session is None:
        return console.input(f"\n[bold {_PROMPT}]› [/bold {_PROMPT}]").strip()
    return prompt_session.prompt(_ansi_prompt_text(mode_code)).strip()


def _handle_slash_command(
    agent: Agent,
    user_input: str,
    reprint_banner: Callable[[], None] | None = None,
) -> bool:
    """Handle one slash command.

    Returns True when the caller should continue the REPL loop.
    Returns False when the command requests REPL exit.
    """
    global _verbose_tools

    parts = user_input[1:].split(maxsplit=1)
    cmd = parts[0].lower() if parts and parts[0] else ""
    arg = parts[1].strip() if len(parts) > 1 else None

    if cmd in ("exit", "quit", "q"):
        return False
    if cmd == "help":
        _show_help()
    elif cmd == "mode":
        from agent.mode import ALL_MODES, parse_mode as _parse_mode, mode_label, mode_colour, mode_description
        from agent.config import update_global_config_values
        from pathlib import Path as _Path

        if not arg:
            # Show current mode + all available modes
            console.print()
            for m in ALL_MODES:
                col  = mode_colour(m)
                mark = "●" if m == agent.mode else "○"
                active = "  [dim](current)[/dim]" if m == agent.mode else ""
                console.print(
                    f"  [{col}]{mark}[/{col}]  [bold {col}]{mode_label(m)}[/bold {col}]"
                    f"  [dim]{mode_description(m)}[/dim]{active}"
                )
            console.print()
            console.print("[dim]  /mode <name>   — switch mode this session[/dim]")
            console.print("[dim]  /mode save     — save to project .env[/dim]")
            console.print("[dim]  /mode save global — save as global default[/dim]")
            console.print()

        elif arg.startswith("save"):
            scope  = "global" if "global" in arg else "project"
            val    = agent.mode.value
            if scope == "global":
                update_global_config_values({"AGENT_MODE": val})
                console.print(f"  [dim]Mode [bold]{val}[/bold] saved to global config.[/dim]")
            else:
                env_path = _Path(".env")
                lines = env_path.read_text().splitlines() if env_path.exists() else []
                lines = [line for line in lines if not line.startswith("AGENT_MODE=")]
                lines.append(f"AGENT_MODE={val}")
                env_path.write_text("\n".join(lines) + "\n")
                console.print(f"  [dim]Mode [bold]{val}[/bold] saved to .env[/dim]")

        else:
            new_mode = _parse_mode(arg)
            if new_mode is None:
                names = " | ".join(m.value for m in ALL_MODES)
                console.print(f"[yellow]Unknown mode '{arg}'. Choose: {names}[/yellow]")
            else:
                agent.set_mode(new_mode)
                col = mode_colour(new_mode)
                console.print(
                    f"\n  [{col}]●[/{col}]  [bold {col}]{mode_label(new_mode)}[/bold {col}]"
                    f"  [dim]{mode_description(new_mode)}[/dim]"
                )
                console.print("[dim]  /mode save to persist to this project's .env[/dim]\n")

    elif cmd == "bg":
        from agent.tools.process import _BACKGROUND_PROCS
        if not _BACKGROUND_PROCS:
            console.print("[dim]No background processes in this session.[/dim]")
        else:
            tail = int(arg) if arg and arg.isdigit() else 10
            for pid, info in _BACKGROUND_PROCS.items():
                proc = info["proc"]
                running = proc.poll() is None
                status_style = "bold green" if running else "dim red"
                status_text = "running" if running else f"exited ({proc.returncode})"
                port_str = f"  port {info['port']}" if info["port"] else ""
                title = Text.assemble(
                    (f"PID {pid}", "bold"),
                    ("  ", ""),
                    (status_text, status_style),
                    (port_str, _MUTED),
                    (f"  started {info['started']}", _MUTED),
                )
                recent = list(info["buf"])[-tail:]
                if recent:
                    output_text = "\n".join(recent)
                    body = Group(
                        Text(info["command"], style="bold cyan"),
                        Rule(style="dim"),
                        Syntax(output_text, "text", theme="monokai",
                               background_color="default", word_wrap=True),
                    )
                else:
                    body = Group(
                        Text(info["command"], style="bold cyan"),
                        Text("(no output yet)", style=_MUTED),
                    )
                border = "bright_green" if running else "dim"
                console.print(Panel(body, title=title, title_align="left",
                                    border_style=border, padding=(0, 1)))
    elif cmd == "init":
        force = arg == "--force"
        from agent.init_cmd import run_init
        run_init(force=force)
        new_content = load_llama_md()
        if new_content:
            console.print("[dim]LLAMA.md will be used from next session (or /reset to reload now).[/dim]")
    elif cmd == "refresh":
        from agent.init_cmd import run_init
        run_init(force=True)
        new_content = load_llama_md()
        if new_content:
            console.print("[dim]LLAMA.md refreshed — use /reset to reload context now.[/dim]")
    elif cmd == "undo":
        if not arg:
            console.print("[yellow]Usage: /undo <file_path>[/yellow]")
        else:
            p = Path(arg)
            bak = p.with_suffix(p.suffix + ".bak")
            if not bak.exists():
                console.print(f"[red]No backup found: {bak}[/red]")
            else:
                import shutil
                shutil.copy2(bak, p)
                console.print(f"[green]Restored {p} from {bak}[/green]")
    elif cmd == "clear":
        # Clear the screen and reprint dashboard — conversation history is kept
        _clear_screen()
        if reprint_banner:
            reprint_banner()
    elif cmd == "rewind":
        from agent.core import _MAX_SNAPSHOTS
        n = int(arg) if arg and arg.isdigit() else 1
        available = len(agent._snapshots)
        turns_before = agent.get_turns()
        rewound = agent.rewind(n)
        if rewound == 0:
            console.print("[dim]Nothing to rewind — conversation is already empty.[/dim]")
        else:
            removed = turns_before[-rewound:]
            turns_after = agent.get_turns()
            table = Table(show_header=False, box=None, padding=(0, 1))
            table.add_column("", style="red dim")
            table.add_column("", style="dim")
            for msg in removed:
                snippet = msg[:80] + ("…" if len(msg) > 80 else "")
                table.add_row("✕", snippet)
            title = f"[bold]Rewound {rewound} turn{'s' if rewound != 1 else ''}[/bold]"
            if rewound < n:
                title += f" [dim](capped at {_MAX_SNAPSHOTS} rewindable turns)[/dim]"
            console.print(Panel(table, title=title, border_style="dim"))
            remaining_label = f"{len(turns_after)} turn{'s' if len(turns_after) != 1 else ''} remaining"
            if available > rewound:
                remaining_label += f" · {available - rewound} more rewindable"
            console.print(f"[dim]{remaining_label}[/dim]")
    elif cmd == "reset":
        # Clear screen, wipe history, reload LLAMA.md — starts a fresh session
        _clear_screen()
        llama_md = load_llama_md()
        context_parts: list[str] = []
        if llama_md:
            context_parts.append(f"## LLAMA.md (project knowledge)\n{llama_md}")
        agent.reset(context_text="\n\n---\n\n".join(context_parts))
        if reprint_banner:
            reprint_banner()
        console.print("[dim]Conversation history cleared — new session started.[/dim]")
    elif cmd == "add":
        if not arg:
            console.print("[yellow]Usage: /add <file_path>[/yellow]")
        else:
            _add_file_to_context(agent, arg)
    elif cmd == "model":
        if not arg:
            console.print(f"[dim]Active model: [bold]{config.llama_model}[/bold][/dim]")
            console.print("[dim]Switch GGUF: ./scripts/switch_model.sh /path/to/model.gguf[/dim]")
        else:
            config.llama_model = arg
            console.print(f"[dim]Model → [bold]{arg}[/bold][/dim]")
    elif cmd == "tools":
        _show_tools()
    elif cmd == "tool":
        if not arg:
            console.print("[yellow]Usage: /tool <name>[/yellow]")
        else:
            _show_tool_detail(arg)
    elif cmd == "history":
        full = len(agent.history)
        windowed = len(agent._windowed_history())
        console.print(
            f"[dim]{full} total msgs · {windowed} in window "
            f"(window={config.history_window} turns)[/dim]"
        )
    elif cmd == "verbose":
        _verbose_tools = not _verbose_tools
        state = "[green]on[/green]" if _verbose_tools else "[dim]off[/dim]"
        console.print(f"[dim]Tool output: {state}[/dim]")
    elif cmd == "cost":
        from agent.stats import session_stats
        console.print(f"[bold]Session stats:[/bold] {session_stats.summary()}")
    elif cmd == "trust":
        from agent.trust import list_trusted, revoke as trust_revoke
        if arg and arg.startswith("revoke "):
            key = arg[7:].strip()
            removed = trust_revoke(key, "project") or trust_revoke(key, "global")
            if removed:
                console.print(f"[dim]Revoked trust: {key}[/dim]")
            else:
                console.print(f"[yellow]Not found: {key}[/yellow]")
        else:
            proj   = list_trusted("project")
            global_ = list_trusted("global")
            table = Table(show_header=True, box=None, padding=(0, 2))
            table.add_column("key", style="bold")
            table.add_column("scope", style="dim")
            for k in sorted(proj):
                table.add_row(k, "project")
            for k in sorted(global_):
                table.add_row(k, "global")
            if proj or global_:
                console.print(Panel(table, title="[bold]Trusted entries[/bold]",
                                    border_style="dim"))
                console.print("[dim]/trust revoke <key> to remove an entry[/dim]")
            else:
                console.print("[dim]No trust entries saved.[/dim]")
    elif cmd == "save":
        path = session.save(agent.history, name=arg)
        console.print(f"[dim]Saved: {path}[/dim]")
    elif cmd == "load":
        if not arg:
            console.print("[yellow]Usage: /load <session_filename>[/yellow]")
        else:
            try:
                agent.history = session.load(arg)
                console.print(f"[dim]Loaded: {arg} ({len(agent.history)} messages)[/dim]")
            except FileNotFoundError as e:
                console.print(f"[red]{e}[/red]")
    elif cmd == "sessions":
        names = session.list_sessions()
        for name in names:
            console.print(f"  [dim]{name}[/dim]")
        if not names:
            console.print("[dim](no saved sessions)[/dim]")
    elif cmd == "memory":
        keys = memory.list_memories()
        console.print("[bold]Memory:[/bold]", ", ".join(keys) if keys else "(none)")
    elif cmd == "forget":
        if not arg:
            console.print("[yellow]Usage: /forget <key>[/yellow]")
        else:
            console.print(memory.forget(arg))
    elif cmd == "":
        _show_help()
    else:
        console.print(f"[yellow]Unknown command: {user_input}  (try /help)[/yellow]")

    return True


# ── /add helper ───────────────────────────────────────────────────────────────

def _add_file_to_context(agent: Agent, path_str: str):
    """Attach one or more files to context. Supports glob patterns."""
    matches = _glob.glob(path_str, recursive=True)
    files = [Path(m) for m in sorted(matches) if Path(m).is_file()]

    if not files:
        # Fallback: treat as literal path
        p = Path(path_str)
        if not p.exists() or not p.is_file():
            console.print(f"[red]File not found: {path_str}[/red]")
            return
        files = [p]

    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        suffix = p.suffix.lstrip(".") or "text"
        agent.history.append({"role": "user", "content": f"Attaching `{p}`:\n\n```{suffix}\n{text}\n```"})
        agent.history.append({"role": "assistant", "content": f"Got it — read `{p}` ({len(text.splitlines())} lines)."})
        console.print(f"[dim]Added {p} ({len(text.splitlines())} lines)[/dim]")


# ── Watch mode ────────────────────────────────────────────────────────────────

def _watch_mode(agent: Agent, watch_path: str):
    """Monitor a file for changes and run a prompt each time it's modified."""
    import time

    p = Path(watch_path)
    if not p.exists():
        console.print(f"[red]Watch file not found: {watch_path}[/red]")
        return

    prompt_template = console.input(
        f"[dim]Watching [bold]{p}[/bold] — enter prompt template "
        f"(use {{content}} for file contents, {{path}} for path):[/dim]\n> "
    ).strip()
    if not prompt_template:
        prompt_template = "The file {path} was updated. Here is the new content:\n\n{content}\n\nReview it and suggest improvements."

    console.print(f"[dim]Watching {p} for changes. Ctrl+C to stop.[/dim]")
    last_mtime = p.stat().st_mtime

    try:
        while True:
            time.sleep(1)
            try:
                mtime = p.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime != last_mtime:
                last_mtime = mtime
                content = p.read_text(encoding="utf-8", errors="ignore")
                prompt = prompt_template.format(path=str(p), content=content)
                console.print(f"\n[bold yellow]File changed:[/bold yellow] {p}")
                _run_turn(agent, prompt, show_bubble=False)
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped.[/dim]")


# ── CLI entry point ───────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--task",        "-t", default=None,  help="Run a single task non-interactively.")
@click.option("--context",     "-c", default=None,  help="Directory to inject as project context.")
@click.option("--resume",      "-r", default=None,  help="Resume a saved session by filename.")
@click.option("--unsafe",      is_flag=True,        help="Skip confirmation prompts.")
@click.option("--model",       "-m", default=None,  help="Override model name.")
@click.option("--no-autosave", is_flag=True,        help="Disable auto-save on exit.")
@click.option("--setup",       is_flag=True,        help="Re-run the first-run setup wizard.")
@click.option("--init",        is_flag=True,        help="Generate LLAMA.md for this project and exit.")
@click.option("--watch",       "-w", default=None,  help="Watch a file; re-run prompt each time it changes.")
@click.pass_context
def main(ctx, task, context, resume, unsafe, model, no_autosave, setup, init, watch):
    """llama-agentic — local AI agent powered by llama.cpp

    Run from any project directory. If a LLAMA.md file exists here it is
    automatically loaded as project context. Use /init to generate one.
    """
    # If a subcommand was invoked, let it handle execution
    if ctx.invoked_subcommand is not None:
        return

    # ── First-run / forced setup (interactive only) ───────────────────────────
    if setup:
        from agent.setup import run_setup
        run_setup()
        return
    if is_first_run() and not task and not init:
        from agent.setup import run_setup
        if not run_setup():
            return

    # ── Apply CLI overrides ───────────────────────────────────────────────────
    if unsafe:
        config.unsafe_mode = True
    if model:
        config.llama_model = model

    # ── Per-project data dirs when LLAMA.md is present ───────────────────────
    llama_md_content = load_llama_md()
    if llama_md_content is not None:
        use_project_data_dirs()

    # ── Build context ─────────────────────────────────────────────────────────
    # LLAMA.md takes priority; --context adds extra file-tree info on top
    context_parts: list[str] = []
    if llama_md_content:
        context_parts.append(f"## LLAMA.md (project knowledge)\n{llama_md_content}")
    if context:
        ctx_text = _build_context(context)
        if ctx_text:
            context_parts.append(ctx_text)
    context_text = "\n\n---\n\n".join(context_parts)

    # ── --init flag: generate LLAMA.md and exit ───────────────────────────────
    if init:
        from agent.init_cmd import run_init
        run_init(yes=unsafe)  # --unsafe also skips write confirmation
        return

    # ── Server health check / auto-start ─────────────────────────────────────
    ok, msg = ensure_server()
    if not ok:
        console.print(f"[red]Server not available:[/red] {msg}")
        return

    from agent.mode import parse_mode as _parse_mode, Mode as _Mode
    confirm_cb = None if config.unsafe_mode else _confirm_tool
    initial_mode = _parse_mode(config.agent_mode) or _Mode.HYBRID
    agent = Agent(confirm_callback=confirm_cb, context_text=context_text, mode=initial_mode)

    if resume:
        try:
            agent.history = session.load(resume)
            console.print(f"[dim]Session loaded: {resume} ({len(agent.history)} messages)[/dim]")
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")

    # ── Non-interactive task mode ─────────────────────────────────────────────
    if task:
        _run_turn(agent, task, show_bubble=False)
        if not no_autosave and agent.history:
            saved = session.save(agent.history, name="task")
            console.print(f"[dim]Session saved → {Path(saved).name}[/dim]")
        return

    # ── Watch mode ────────────────────────────────────────────────────────────
    if watch:
        _watch_mode(agent, watch)

    # ── Interactive REPL ──────────────────────────────────────────────────────
    cwd = Path.cwd()
    from agent.mcp_client import get_manager
    mcp_servers = get_manager().connected_servers
    from agent.a2a_client import get_manager as get_a2a_manager
    a2a_agents = get_a2a_manager().connected_agents

    # Build status pills
    pills: list[str] = [f"[bold green]{config.llama_model}[/bold green]"]
    if llama_md_content:
        pills.append("[dim cyan]LLAMA.md[/dim cyan]")
    if mcp_servers:
        pills.append(f"[dim magenta]MCP: {', '.join(mcp_servers)}[/dim magenta]")
    if a2a_agents:
        pills.append(f"[dim blue]A2A: {', '.join(a2a_agents)}[/dim blue]")

    from agent.mode import prompt_ansi_code as _mode_ansi

    def _reprint_banner() -> None:
        _print_banner(
            cwd,
            cwd.name,
            config.llama_model,
            has_llama_md=bool(load_llama_md()),
            has_mcp=bool(mcp_servers),
            has_a2a=bool(a2a_agents),
            agent_mode=agent.mode,
        )

    _reprint_banner()
    prompt_session = _build_prompt_session()

    try:
        while True:
            try:
                user_input = _read_repl_input(prompt_session, _mode_ansi(agent.mode))
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                if not _handle_slash_command(agent, user_input, reprint_banner=_reprint_banner):
                    break
                continue

            _run_turn(agent, user_input, show_bubble=False)

    finally:
        # Kill any background processes started during this session
        from agent.tools.process import kill_all_background
        n = kill_all_background()
        if n:
            console.print(f"\n[dim]Stopped {n} background process{'es' if n != 1 else ''}.[/dim]")

        if not no_autosave and agent.history:
            saved = session.save(agent.history, name="chat")
            console.print(f"\n[dim]Session saved → {Path(saved).name}[/dim]")
        console.print()
        console.print("[dim]Goodbye.[/dim]")


@main.group("mcp")
def cmd_mcp():
    """Manage MCP (Model Context Protocol) servers."""


@cmd_mcp.command("list")
def cmd_mcp_list():
    """List configured MCP servers and their tools."""
    from agent.mcp_config import load_mcp_config, GLOBAL_MCP_FILE, LOCAL_MCP_FILE
    from pathlib import Path

    servers = load_mcp_config()
    if not servers:
        console.print("[dim]No MCP servers configured.[/dim]")
        console.print(f"[dim]Global config: {GLOBAL_MCP_FILE}[/dim]")
        console.print("[dim]Add one with: llama-agent mcp add <name>[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Name")
    table.add_column("Transport")
    table.add_column("Command / URL")
    table.add_column("Status", justify="center")

    for name, srv in servers.items():
        status = "[green]enabled[/green]" if srv.enabled else "[dim]disabled[/dim]"
        if srv.transport == "http":
            cmd_str = srv.url
        else:
            cmd_str = " ".join([srv.command] + srv.args[:2])
            if len(srv.args) > 2:
                cmd_str += " …"
        table.add_row(name, srv.transport, cmd_str, status)

    console.print(table)
    local_exists = Path(LOCAL_MCP_FILE).exists()
    console.print(f"\n[dim]Global: {GLOBAL_MCP_FILE}[/dim]")
    if local_exists:
        console.print(f"[dim]Project: {LOCAL_MCP_FILE}[/dim]")


@cmd_mcp.command("add")
@click.argument("name")
@click.option("--command", "-c", default=None, help="Command to launch the server (stdio).")
@click.option("--args",    "-a", default="", help="Space-separated args for the command.")
@click.option("--url",     "-u", default=None, help="HTTP server URL (alternative to stdio).")
@click.option("--desc",    "-d", default="", help="Optional description.")
@click.option("--local",   is_flag=True, help="Save to per-project .llama-agentic/mcp.json.")
def cmd_mcp_add(name, command, args, url, desc, local):
    """Add an MCP server to the configuration.

    Examples:
      llama-agent mcp add filesystem --command npx --args "-y @modelcontextprotocol/server-filesystem /"
      llama-agent mcp add myserver --url http://localhost:3000
    """
    from agent.mcp_config import MCPServerConfig, add_server

    if not command and not url:
        console.print("[red]Provide either --command (stdio) or --url (HTTP).[/red]")
        return

    srv = MCPServerConfig(
        name=name,
        command=command or "",
        args=args.split() if args else [],
        url=url or "",
        description=desc,
        enabled=True,
    )
    add_server(name, srv, global_=not local)
    scope = "project" if local else "global"
    console.print(f"[green]Added MCP server:[/green] {name} ({scope})")
    console.print("[dim]Start the agent to auto-connect, or run: llama-agent mcp list[/dim]")


@cmd_mcp.command("remove")
@click.argument("name")
@click.option("--local", is_flag=True, help="Remove from per-project config.")
def cmd_mcp_remove(name, local):
    """Remove an MCP server from the configuration."""
    from agent.mcp_config import remove_server

    removed = remove_server(name, global_=not local)
    if removed:
        console.print(f"[green]Removed:[/green] {name}")
    else:
        console.print(f"[yellow]Not found:[/yellow] {name}")


@cmd_mcp.command("connect")
@click.argument("name")
def cmd_mcp_connect(name):
    """Test-connect to a single MCP server and list its tools."""
    from agent.mcp_config import load_mcp_config
    from agent.mcp_client import make_client

    servers = load_mcp_config()
    if name not in servers:
        console.print(f"[red]Unknown server:[/red] {name}. Run: llama-agent mcp list")
        return

    srv_config = servers[name]
    console.print(f"Connecting to [bold]{name}[/bold] ({srv_config.transport}) …")
    try:
        client = make_client(srv_config)
        client.start()
        tools = client.list_tools()
        client.stop()

        if not tools:
            console.print("[dim](no tools exposed)[/dim]")
            return

        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Tool")
        table.add_column("Description", style="dim")
        for t in tools:
            table.add_row(t["name"], t.get("description", ""))
        console.print(table)
        console.print(f"\n[green]{len(tools)} tools available from {name}[/green]")
    except Exception as e:
        console.print(f"[red]Connection failed:[/red] {e}")


@main.group("a2a")
def cmd_a2a():
    """Manage A2A (Agent-to-Agent) agents."""


@cmd_a2a.command("list")
def cmd_a2a_list():
    """List configured A2A agents."""
    from agent.a2a_config import GLOBAL_A2A_FILE, LOCAL_A2A_FILE, load_a2a_config

    agents = load_a2a_config()
    if not agents:
        console.print("[dim]No A2A agents configured.[/dim]")
        console.print(f"[dim]Global config: {GLOBAL_A2A_FILE}[/dim]")
        console.print("[dim]Add one with: llama-agent a2a add <name> --url <url>[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Name")
    table.add_column("URL")
    table.add_column("Status", justify="center")
    table.add_column("Description", style="dim")

    for name, agent_cfg in agents.items():
        status = "[green]enabled[/green]" if agent_cfg.enabled else "[dim]disabled[/dim]"
        table.add_row(name, agent_cfg.url, status, agent_cfg.description or "")

    console.print(table)
    console.print(f"\n[dim]Global: {GLOBAL_A2A_FILE}[/dim]")
    if LOCAL_A2A_FILE.exists():
        console.print(f"[dim]Project: {LOCAL_A2A_FILE}[/dim]")


@cmd_a2a.command("add")
@click.argument("name")
@click.option("--url", "-u", required=True, help="A2A base URL or Agent Card URL.")
@click.option("--desc", "-d", default="", help="Optional description.")
@click.option("--local", is_flag=True, help="Save to per-project .llama-agentic/a2a.json.")
def cmd_a2a_add(name, url, desc, local):
    """Add an A2A agent to the configuration."""
    from agent.a2a_config import A2AAgentConfig, add_agent

    add_agent(
        name,
        A2AAgentConfig(name=name, url=url, description=desc, enabled=True),
        global_=not local,
    )
    scope = "project" if local else "global"
    console.print(f"[green]Added A2A agent:[/green] {name} ({scope})")
    console.print("[dim]Test it with: llama-agent a2a connect <name>[/dim]")


@cmd_a2a.command("remove")
@click.argument("name")
@click.option("--local", is_flag=True, help="Remove from per-project config.")
def cmd_a2a_remove(name, local):
    """Remove an A2A agent from the configuration."""
    from agent.a2a_config import remove_agent

    removed = remove_agent(name, global_=not local)
    if removed:
        console.print(f"[green]Removed:[/green] {name}")
    else:
        console.print(f"[yellow]Not found:[/yellow] {name}")


@cmd_a2a.command("connect")
@click.argument("name")
def cmd_a2a_connect(name):
    """Fetch an Agent Card and show the agent's available skills."""
    from agent.a2a_client import A2AClient
    from agent.a2a_config import load_a2a_config

    agents = load_a2a_config()
    if name not in agents:
        console.print(f"[red]Unknown A2A agent:[/red] {name}. Run: llama-agent a2a list")
        return

    client = A2AClient(agents[name])
    console.print(f"Connecting to [bold]{name}[/bold] …")

    try:
        client.start()
        card = client.card or {}
        rpc_url = client.rpc_url or agents[name].url
        title = card.get("name") or name
        description = card.get("description") or agents[name].description or ""

        console.print(f"[green]Connected:[/green] {title}")
        console.print(f"[dim]RPC URL:[/dim] {rpc_url}")
        if description:
            console.print(f"[dim]{description}[/dim]")

        skills = client.list_skills()
        if not skills:
            console.print("[dim](no skills declared in the Agent Card)[/dim]")
            return

        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Skill")
        table.add_column("Description", style="dim")
        for skill in skills:
            skill_name = skill.get("name") or skill.get("id") or "(unnamed)"
            table.add_row(str(skill_name), str(skill.get("description", "")))
        console.print(table)
        console.print(f"\n[green]{len(skills)} skills available from {name}[/green]")
    except Exception as e:
        console.print(f"[red]Connection failed:[/red] {e}")
    finally:
        client.stop()


@main.command("doctor")
def cmd_doctor():
    """Check environment: llama-server, models, config."""
    from agent.doctor import run_doctor
    run_doctor()


@main.command("download")
@click.argument("model", default="", required=False)
@click.option("--filename", "-f", default=None, help="Filename in HF repo (for raw repo IDs).")
@click.option("--dest",     "-d", default=None, help="Override destination directory.")
def cmd_download(model, filename, dest):
    """Download a GGUF model from Hugging Face Hub.

    MODEL can be a short alias (e.g. qwen2.5-coder-7b) or a HF repo ID.
    Run without arguments to list known aliases.
    """
    from agent.model_manager import download, list_known, find_models, persist_selected_model
    from agent.config import config

    if not model:
        console.print("[bold]Known model aliases:[/bold]")
        for alias in list_known():
            console.print(f"  [cyan]{alias}[/cyan]")
        console.print(
            f"\n[dim]Models are cached in: {config.model_cache_dir}[/dim]"
        )
        existing = find_models()
        if existing:
            console.print("\n[bold]Already downloaded:[/bold]")
            for p in existing:
                console.print(f"  [green]{p.name}[/green]  [dim]{p}[/dim]")
        return

    console.print(f"Downloading [bold]{model}[/bold] …")
    try:
        path = download(alias_or_repo=model, filename=filename, dest_dir=dest)
        persisted = persist_selected_model(path)
        console.print(f"[green]Saved to:[/green] {path}")
        console.print(f"[dim]Configured LLAMA_MODEL_PATH → {persisted}[/dim]")
        console.print("[dim]Tip: set LLAMA_MODEL in your config or use --model to activate it.[/dim]")
    except Exception as e:
        console.print(f"[red]Download failed:[/red] {e}")


@main.group("autostart")
def cmd_autostart():
    """Manage llama-server auto-start on system boot."""


@cmd_autostart.command("enable")
@click.option("--model", "-m", default=None, help="Path to GGUF model file.")
def cmd_autostart_enable(model):
    """Register llama-server to start automatically at login/boot."""
    from agent.autostart import enable
    try:
        msg = enable(model_path=model)
        console.print(f"[green]✓[/green] {msg}")
        console.print("[dim]The server will start next time you log in.[/dim]")
        console.print("[dim]To start it now without rebooting, run: llama-agent autostart start[/dim]")
    except RuntimeError as e:
        console.print(f"[red]Failed:[/red] {e}")


@cmd_autostart.command("disable")
def cmd_autostart_disable():
    """Remove the llama-server boot service."""
    from agent.autostart import disable
    msg = disable()
    console.print(f"[dim]{msg}[/dim]")


@cmd_autostart.command("status")
def cmd_autostart_status():
    """Show whether the boot service is enabled."""
    from agent.autostart import status
    msg = status()
    if msg.startswith("Enabled"):
        console.print(f"[green]{msg}[/green]")
    else:
        console.print(f"[dim]{msg}[/dim]")


@cmd_autostart.command("start")
def cmd_autostart_start():
    """Start the llama-server right now (without waiting for reboot)."""
    from agent.server_manager import start_server, resolve_model_file
    from agent.config import config
    model = resolve_model_file()
    if not model:
        console.print(f"[red]No model found in {config.model_cache_dir}[/red]")
        console.print("[dim]Download one: llama-agent download qwen2.5-coder-7b[/dim]")
        return
    console.print(f"Starting llama-server with [bold]{model}[/bold] …")
    ok = start_server(model_path=model)
    if ok:
        console.print("[green]✓ Server is running.[/green]")
    else:
        console.print("[red]Server failed to start. Run: llama-agent doctor[/red]")


@main.command("update")
def cmd_update():
    """Upgrade llama-agentic to the latest version from PyPI."""
    import subprocess
    import sys
    console.print("Checking for updates …")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "llama-agentic"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        # Extract version info from pip output
        for line in result.stdout.splitlines():
            if "Successfully installed" in line or "already up-to-date" in line.lower() or "already satisfied" in line.lower():
                console.print(f"[green]{line}[/green]")
                break
        else:
            console.print("[green]Update complete.[/green]")
    else:
        console.print(f"[red]Update failed:[/red] {result.stderr.strip()}")


@main.command("completions")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]), default="bash")
def cmd_completions(shell):
    """Print shell completion script.

    Usage:
      bash:  eval "$(llama-agent completions bash)"
      zsh:   eval "$(llama-agent completions zsh)"
      fish:  llama-agent completions fish | source
    """
    import os
    env_var = f"_{main.name.upper().replace('-', '_')}_COMPLETE"
    shell_complete = {"bash": "bash_source", "zsh": "zsh_source", "fish": "fish_source"}
    os.environ[env_var] = shell_complete[shell]
    try:
        main(standalone_mode=False)
    except SystemExit:
        pass


@main.command("models")
def cmd_models():
    """List GGUF models in the model cache."""
    from agent.model_manager import find_models
    from agent.config import config, configured_model_path

    models = find_models()
    if not models:
        console.print(f"[dim]No models in {config.model_cache_dir}[/dim]")
        console.print("[dim]Download one with: llama-agent download[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Model")
    table.add_column("Size", justify="right")
    table.add_column("Selected", justify="center")
    table.add_column("Path", style="dim")
    selected = configured_model_path()
    for p in models:
        size_mb = p.stat().st_size / (1024 * 1024)
        marker = "yes" if selected and p.resolve() == selected else ""
        table.add_row(p.name, f"{size_mb:.0f} MB", marker, str(p.parent))
    console.print(table)


if __name__ == "__main__":
    main()
