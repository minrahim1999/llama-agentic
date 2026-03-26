"""'/init' command — generate LLAMA.md for the current project using the LLM."""

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

console = Console()

LLAMA_MD = Path("LLAMA.md")

# Files that reveal the tech stack and purpose
_KEY_FILES = [
    "README.md", "README", "README.rst",
    "pyproject.toml", "setup.py", "requirements.txt",
    "package.json", "tsconfig.json",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
    "Makefile", "Dockerfile", "docker-compose.yml",
    ".env.example",
    "CLAUDE.md",  # if migrating from Claude Code
]
_MAX_FILE_CHARS = 3000
_SKIP_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache",
    "node_modules", ".llama-agentic", ".claude",
    "dist", "build", "target", ".next",
}


def _gather_project_info() -> str:
    """Collect project info: tree + key file contents."""
    cwd = Path.cwd()
    sections: list[str] = [f"# Project root: {cwd}\n"]

    # Directory tree
    tree: list[str] = []
    for entry in sorted(cwd.rglob("*")):
        if any(part in _SKIP_DIRS for part in entry.parts):
            continue
        rel = entry.relative_to(cwd)
        depth = len(rel.parts) - 1
        icon = "F" if entry.is_file() else "D"
        tree.append("  " * depth + f"[{icon}] {entry.name}")
        if len(tree) >= 100:
            tree.append("  ... (truncated)")
            break
    sections.append("## Directory tree\n" + "\n".join(tree))

    # Key file contents
    for fname in _KEY_FILES:
        fpath = cwd / fname
        if fpath.exists() and fpath.is_file():
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            if len(text) > _MAX_FILE_CHARS:
                text = text[:_MAX_FILE_CHARS] + f"\n...(truncated, {len(text)} chars total)"
            sections.append(f"## {fname}\n```\n{text}\n```")

    return "\n\n".join(sections)


_SYSTEM_PROMPT = """\
You are an expert technical writer and software architect.
Your task is to generate a LLAMA.md file for a software project.
LLAMA.md is loaded at the start of every AI agent session to give the agent
context about the project. It should be concise, structured, and useful.
"""

_USER_PROMPT_TEMPLATE = """\
Analyse the following project information and generate a LLAMA.md file.

The LLAMA.md must contain these sections (use exactly these headings):

## Project Overview
One paragraph: what the project does, who it's for, the main value it provides.

## Tech Stack
Bullet list of languages, frameworks, key libraries, and tools detected.

## Directory Structure
Key directories and what they contain (skip trivial ones like .git, __pycache__).

## Key Files
The most important files an AI agent should know about, with one-line descriptions.

## How to Run
Commands to: install dependencies, start the app/server, run tests.

## Conventions
Code style, naming patterns, branching strategy, important rules to follow.

## Agent Notes
Critical things an AI coding agent MUST know:
- What files should never be modified
- Which commands need user confirmation before running
- Any gotchas, tricky parts, or non-obvious architecture decisions

---
PROJECT INFORMATION:
{project_info}
"""


def _has_project_files(cwd: Path) -> bool:
    """Return True if cwd contains at least one non-ignored file."""
    for entry in cwd.rglob("*"):
        if any(part in _SKIP_DIRS for part in entry.parts):
            continue
        if entry.is_file() and not entry.name.startswith("."):
            return True
    return False


def run_init(force: bool = False, yes: bool = False) -> None:
    """Generate LLAMA.md in the current directory."""
    cwd = Path.cwd()

    if not _has_project_files(cwd):
        console.print(f"[yellow]No project files found in {cwd} — nothing to analyse.[/yellow]")
        console.print("[dim]Create some files first, then run /init again.[/dim]")
        return

    if LLAMA_MD.exists() and not force and not yes:
        console.print(f"[yellow]LLAMA.md already exists in {cwd}[/yellow]")
        if not Confirm.ask("Overwrite it?", default=False):
            return

    console.print()
    console.print(Rule(f"[bold]init[/bold]  {cwd.name}", style="blue", align="left"))

    with console.status("[dim]Scanning project files…[/dim]", spinner="dots"):
        project_info = _gather_project_info()

    # Stream the LLM response, collecting silently
    from agent.llama_client import get_client
    from agent.config import config

    client = get_client()
    content_parts: list[str] = []

    try:
        with console.status("[dim]Generating LLAMA.md…[/dim]", spinner="dots"):
            stream = client.chat.completions.create(
                model=config.llama_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _USER_PROMPT_TEMPLATE.format(project_info=project_info)},
                ],
                stream=True,
                max_tokens=2048,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    content_parts.append(delta.content)
    except Exception as exc:
        console.print(f"[red]LLM error: {exc}[/red]")
        console.print("[yellow]Falling back to template-only LLAMA.md[/yellow]")
        content_parts = [_fallback_template(cwd)]

    final_content = "".join(content_parts).strip()

    # Prepend header
    header = (
        f"# LLAMA.md — {cwd.name}\n\n"
        f"> Auto-generated by llama-agentic `/init`  \n"
        f"> Loaded at the start of every agent session as project context.  \n"
        f"> Edit this file to keep it accurate as the project evolves.\n\n"
    )
    full_content = header + final_content

    # Show as a distinct file-preview panel, not a chat response
    console.print()
    console.print(
        Panel(
            Syntax(full_content, "markdown", theme="nord", word_wrap=True, line_numbers=False),
            title=Text.assemble(("  LLAMA.md", "bold white"), ("  preview", "dim")),
            title_align="left",
            border_style="blue",
            subtitle=f"[dim]{len(full_content)} chars[/dim]",
            subtitle_align="right",
            padding=(0, 1),
        )
    )
    console.print()

    # Confirm before writing
    if not yes and not Confirm.ask(f"Write to {cwd / 'LLAMA.md'}?", default=True):
        console.print("[dim]Aborted — nothing written.[/dim]")
        return

    LLAMA_MD.write_text(full_content, encoding="utf-8")
    console.print(f"[green]✓[/green] [bold]LLAMA.md[/bold] written  [dim]{cwd / 'LLAMA.md'}[/dim]")
    console.print("[dim]Loaded automatically next time you run llama-agent here.[/dim]")


def _fallback_template(cwd: Path) -> str:
    """Minimal template when LLM is unavailable."""
    return """\
## Project Overview
*(fill in: what this project does)*

## Tech Stack
*(fill in: languages, frameworks, tools)*

## Directory Structure
*(fill in: key directories)*

## Key Files
*(fill in: important files)*

## How to Run
*(fill in: install, start, test commands)*

## Conventions
*(fill in: code style, naming, rules)*

## Agent Notes
*(fill in: things the AI agent must know)*
"""


def load_llama_md() -> str | None:
    """Read LLAMA.md from cwd if it exists. Returns content or None."""
    if LLAMA_MD.exists():
        return LLAMA_MD.read_text(encoding="utf-8", errors="ignore")
    return None
