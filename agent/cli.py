"""Interactive CLI for the llama-agentic agent."""

import glob as _glob
import json
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from agent.config import config, is_first_run, use_project_data_dirs
from agent.core import Agent
from agent import memory, session
from agent.server_manager import ensure_server
from agent.tools.edit import compute_diff
from agent.init_cmd import load_llama_md

console = Console()

_CONTEXT_READ_FILES = {"CLAUDE.md", "README.md", "README", "pyproject.toml", "package.json"}
_CONTEXT_FILE_LIMIT = 2000
_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".claude", ".llama-agentic"}

# Show full tool output (toggled by /verbose)
_verbose_tools: bool = False


# ── Confirmation ──────────────────────────────────────────────────────────────

def _confirm_tool(name: str, args: dict) -> bool:
    if name == "edit_file":
        path = args.get("path", "")
        diff_text = compute_diff(path, args.get("old_string", ""), args.get("new_string", ""))
        console.print(Panel(
            Syntax(diff_text, "diff", theme="monokai", line_numbers=False),
            title=f"[red]edit_file[/red] → [bold]{path}[/bold]",
            border_style="yellow",
        ))
    else:
        console.print(Panel(
            f"[yellow]Tool:[/yellow] [bold]{name}[/bold]\n\n[dim]{json.dumps(args, indent=2)}[/dim]",
            title="[red]Confirmation required[/red]",
            border_style="yellow",
        ))
    return Confirm.ask("Allow this action?", default=False)


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

def _print_user_bubble(text: str):
    """Render the user's message as a right-aligned chat bubble."""
    console.print()
    console.print(Panel(
        f"[bold]{text}[/bold]",
        title="[bold blue]You[/bold blue]",
        title_align="right",
        border_style="blue",
        padding=(0, 1),
    ))


def _tool_status(chunk: str) -> tuple[str, str]:
    """Parse '\n[tool: name]\nfull_output\n' → (name, full_output)."""
    lines = chunk.strip().split("\n", 1)  # header + ALL output
    header = lines[0]
    name = header.replace("[tool:", "").replace("]", "").strip()
    output = lines[1] if len(lines) > 1 else ""
    return name, output


# ── Agent runner ──────────────────────────────────────────────────────────────

def _run_turn(agent: Agent, user_input: str, show_bubble: bool = True):
    from agent.stats import session_stats
    global _verbose_tools

    if show_bubble:
        _print_user_bubble(user_input)

    console.print()
    console.print(f" [bold green]Assistant[/bold green]")
    console.print(" " + "─" * 50, style="green dim")

    gen = agent.run(user_input)
    tool_calls_this_turn: list[str] = []

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
            # Markdown headers → bold cyan
            console.print(line, markup=False, style="bold cyan")
        elif stripped.startswith(("- ", "* ", "+ ")):
            # Bullet lists → bright white
            console.print(line, markup=False, style="bright_white")
        else:
            console.print(line, markup=False)

    try:
        while True:
            chunk = next(gen)
            if chunk.startswith("\n[tool:"):
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

                console.print()
                if is_error:
                    console.print(
                        f"  ⚙  [bold]{name}[/bold]  [red]✗[/red]  [red dim]{brief}[/red dim]"
                    )
                else:
                    line = f"  [dim]⚙  {name}[/dim]  [green]✓[/green]"
                    if brief:
                        line += f"  [dim]{brief}[/dim]"
                    console.print(line)
                    if _verbose_tools and output_stripped:
                        console.print(
                            Panel(output_stripped, border_style="dim", padding=(0, 1)),
                            style="dim",
                        )
            else:
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

    console.print()
    console.print(" " + "─" * 50, style="green dim")
    console.print(
        f"  [dim]~{session_stats.estimated_tokens:,} tokens"
        + (f" · {len(tool_calls_this_turn)} tool{'s' if len(tool_calls_this_turn) != 1 else ''}: "
           + ", ".join(tool_calls_this_turn) if tool_calls_this_turn else "")
        + f" · turn {session_stats.turns}[/dim]"
    )


# ── Help ──────────────────────────────────────────────────────────────────────

def _show_help():
    table = Table(show_header=False, box=None, padding=(0, 2))
    cmds = [
        ("/init [--force]",   "Generate LLAMA.md for this project"),
        ("/refresh",          "Re-generate LLAMA.md (update project knowledge)"),
        ("/add <glob>",       "Attach file(s) to context — supports globs"),
        ("/undo <file>",      "Restore last .bak backup of a file"),
        ("/model [name]",     "Show or switch active model"),
        ("/tools",            "List all registered tools"),
        ("/reset",            "Clear conversation history"),
        ("/save [name]",      "Save session to disk"),
        ("/load <name>",      "Resume a saved session"),
        ("/sessions",         "List saved sessions"),
        ("/memory",           "List persistent memory keys"),
        ("/forget <key>",     "Delete a memory entry"),
        ("/history",          "Show context window stats"),
        ("/verbose",          "Toggle full tool output on/off (hidden by default)"),
        ("/cost",             "Show session stats: turns, tool calls, tokens, time"),
        ("/exit",             "Quit"),
    ]
    for cmd, desc in cmds:
        table.add_row(f"[bold]{cmd}[/bold]", desc)
    console.print(Panel(table, title="[bold]Commands[/bold]", border_style="dim"))


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

    confirm_cb = None if config.unsafe_mode else _confirm_tool
    agent = Agent(confirm_callback=confirm_cb, context_text=context_text)

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

    # Build status pills
    pills: list[str] = [f"[bold green]{config.llama_model}[/bold green]"]
    if llama_md_content:
        pills.append("[dim cyan]LLAMA.md[/dim cyan]")
    if mcp_servers:
        pills.append(f"[dim magenta]MCP: {', '.join(mcp_servers)}[/dim magenta]")

    console.print()
    console.print(Panel(
        f"[bold green]llama-agentic[/bold green]  {'  ·  '.join(pills)}\n"
        f"[dim]{cwd}[/dim]\n"
        "[dim]/help for commands  ·  /verbose to toggle tool output  ·  /exit to quit[/dim]",
        border_style="green",
        padding=(0, 1),
    ))

    try:
        while True:
            try:
                user_input = console.input("\n[bold blue] ❯ [/bold blue]").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                parts = user_input[1:].split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1].strip() if len(parts) > 1 else None

                if cmd in ("exit", "quit", "q"):
                    break
                elif cmd == "help":
                    _show_help()
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
                elif cmd == "reset":
                    agent.reset()
                    console.print("[dim]Conversation reset.[/dim]")
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
                    from agent import tools as tr
                    names = sorted(tr._REGISTRY.keys())
                    table = Table(show_header=False, box=None, padding=(0, 2))
                    for n in names:
                        desc = tr._REGISTRY[n]["schema"]["function"]["description"]
                        table.add_row(f"[bold]{n}[/bold]", f"[dim]{desc}[/dim]")
                    console.print(Panel(table, title=f"[bold]Tools ({len(names)})[/bold]", border_style="dim"))
                elif cmd == "history":
                    full = len(agent.history)
                    windowed = len(agent._windowed_history())
                    console.print(
                        f"[dim]{full} total msgs · {windowed} in window "
                        f"(window={config.history_window} turns)[/dim]"
                    )
                elif cmd == "verbose":
                    global _verbose_tools
                    _verbose_tools = not _verbose_tools
                    state = "[green]on[/green]" if _verbose_tools else "[dim]off[/dim]"
                    console.print(f"[dim]Tool output: {state}[/dim]")
                elif cmd == "cost":
                    from agent.stats import session_stats
                    console.print(f"[bold]Session stats:[/bold] {session_stats.summary()}")
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
                    for n in names:
                        console.print(f"  [dim]{n}[/dim]")
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
                else:
                    console.print(f"[yellow]Unknown command: {user_input}  (try /help)[/yellow]")
                continue

            _run_turn(agent, user_input)

    finally:
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
    from agent.model_manager import download, list_known, find_models
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
        console.print(f"[green]Saved to:[/green] {path}")
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
    from agent.server_manager import start_server, _find_model_file
    from agent.config import config
    model = _find_model_file()
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
    from agent.config import config

    models = find_models()
    if not models:
        console.print(f"[dim]No models in {config.model_cache_dir}[/dim]")
        console.print("[dim]Download one with: llama-agent download[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Model")
    table.add_column("Size", justify="right")
    table.add_column("Path", style="dim")
    for p in models:
        size_mb = p.stat().st_size / (1024 * 1024)
        table.add_row(p.name, f"{size_mb:.0f} MB", str(p.parent))
    console.print(table)


if __name__ == "__main__":
    main()
