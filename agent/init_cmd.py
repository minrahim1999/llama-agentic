"""'/init' command — generate LLAMA.md for the current project using the LLM."""

from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm

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


def run_init(force: bool = False, yes: bool = False) -> None:
    """Generate LLAMA.md in the current directory."""
    cwd = Path.cwd()

    if LLAMA_MD.exists() and not force and not yes:
        console.print(f"[yellow]LLAMA.md already exists in {cwd}[/yellow]")
        if not Confirm.ask("Overwrite it?", default=False):
            return

    console.print(f"\n[bold]Initialising project at:[/bold] {cwd}")
    console.print("[dim]Scanning project files...[/dim]")

    project_info = _gather_project_info()

    console.print("[dim]Asking the model to analyse your project...[/dim]\n")

    # Stream the LLM response
    from agent.llama_client import get_client
    from agent.config import config

    client = get_client()
    content_parts: list[str] = []

    try:
        stream = client.chat.completions.create(
            model=config.llama_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_PROMPT_TEMPLATE.format(project_info=project_info)},
            ],
            stream=True,
            max_tokens=2048,
        )
        console.print("[bold cyan]Generated LLAMA.md:[/bold cyan]\n")
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                content_parts.append(delta.content)
                console.print(delta.content, end="")
        console.print("\n")
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

    # Confirm before writing
    console.print()
    if not yes and not Confirm.ask(f"Write LLAMA.md to {cwd}?", default=True):
        console.print("[dim]Aborted — nothing written.[/dim]")
        return

    LLAMA_MD.write_text(full_content, encoding="utf-8")
    console.print(f"[green]✓ LLAMA.md written to {cwd / 'LLAMA.md'}[/green]")
    console.print("[dim]It will be loaded automatically next time you run llama-agent here.[/dim]")


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
