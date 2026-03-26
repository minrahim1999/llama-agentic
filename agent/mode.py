"""Agent execution modes.

Each mode controls:
  - which tools are exposed to the LLM
  - the system-prompt instructions injected
  - how the REPL prompt badge looks

Modes
-----
chat    Conversational only — no write/execute tools.
plan    Planning only — reads freely, writes only PLAN.md, never executes.
code    Direct execution — all tools available, no planning gate.
hybrid  (default) Plan → user approval → execute.
review  Code-review — reads freely, writes only REVIEW.md.
"""
from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    CHAT   = "chat"
    PLAN   = "plan"
    CODE   = "code"
    HYBRID = "hybrid"
    REVIEW = "review"


# ── Tool classification ────────────────────────────────────────────────────────

# Tools that mutate state.  Blocked entirely in chat / review modes.
_MUTATING: set[str] = {
    "write_file", "edit_file", "delete_file", "make_dir",
    "copy_file", "move_file",
    "run_shell", "run_background", "run_python",
    "git_commit", "kill_process", "stop_background",
}

# In plan/review modes we allow write_file (for PLAN.md / REVIEW.md)
# but block everything that executes or mutates source files.
_PLAN_BLOCKED: set[str] = _MUTATING - {"write_file"}


def get_blocked_tools(mode: Mode) -> set[str]:
    """Return the set of tool names the LLM must NOT see in this mode."""
    if mode in (Mode.CHAT,):
        return _MUTATING          # fully read-only
    if mode in (Mode.PLAN, Mode.REVIEW):
        return _PLAN_BLOCKED      # write_file allowed for plan/review output
    return set()                  # CODE and HYBRID: unrestricted


# ── Per-mode system-prompt injections ─────────────────────────────────────────

_INSTRUCTIONS: dict[Mode, str] = {

    Mode.CHAT: """\
## Mode: CHAT
You are in conversational chat mode.
- Respond helpfully and naturally.
- Do NOT use any tools that create, modify, or delete files, or that run commands.
- You MAY use read-only tools (read_file, search, web_fetch) to answer questions.
- If the user asks you to make changes, explain what you would do and suggest they switch to code or hybrid mode.""",

    Mode.PLAN: """\
## Mode: PLAN
You are in planning mode. Produce a plan — do NOT execute anything.
- Read existing files freely to understand the project.
- Write the completed plan to PLAN.md using write_file (the ONLY write operation allowed).
- Structure PLAN.md with: Overview · Phases (numbered) · Steps per phase (file paths, commands, expected outcomes) · Risks and mitigations.
- After writing PLAN.md, give the user a short summary of what the plan covers.
- Never run commands, edit source files, delete anything, or install packages.""",

    Mode.CODE: """\
## Mode: CODE
You are in direct execution mode. Act immediately and efficiently.
- Create, modify, and delete files as needed to complete the task.
- No planning phase required — go straight to work.
- Keep changes minimal and focused.
- Ask the user for clarification only when the intent is genuinely ambiguous.
IMPORTANT: NEVER show file contents or code blocks in your response as a substitute for acting.
Use write_file or edit_file to actually write the changes, then briefly confirm what you did.""",

    Mode.HYBRID: """\
## Mode: HYBRID (default)
For any non-trivial task (file changes, commands, multi-step work):
  1. Think through what needs to be done.
  2. Present a concise plan to the user BEFORE taking any action.
  3. Call ask_choice with options: ["Proceed", "Modify the plan", "Cancel"].
  4. Only execute after the user selects "Proceed" — call write_file / edit_file / run_shell directly.
  5. Optionally save the approved plan to PLAN.md first.
IMPORTANT: After the user approves, DO NOT show code in your response — call write_file or edit_file to make the actual changes.
For simple questions, single-sentence tasks, or pure conversation — respond directly, no planning gate needed.""",

    Mode.REVIEW: """\
## Mode: REVIEW
You are in code-review mode.
- Read and analyse the codebase thoroughly.
- Do NOT modify any source files.
- Write your findings to REVIEW.md (or a filename the user specifies) using write_file.
- Structure the review: Executive Summary · Issues (Critical / Major / Minor) · Suggestions · Positive findings.
- Be specific: include file paths, line references, and concrete recommendations.""",
}


def get_mode_instruction(mode: Mode) -> str:
    return _INSTRUCTIONS.get(mode, "")


# ── Display metadata ───────────────────────────────────────────────────────────

# mode → (short label, hex colour, one-line description)
_DISPLAY: dict[Mode, tuple[str, str, str]] = {
    Mode.CHAT:   ("chat",   "#88c0d0", "Conversational — no file operations or commands"),
    Mode.PLAN:   ("plan",   "#ebcb8b", "Planning only — writes PLAN.md, never executes"),
    Mode.CODE:   ("code",   "#a3be8c", "Direct execution — create / edit / delete freely"),
    Mode.HYBRID: ("hybrid", "#d08770", "Plan → approval → execute  (recommended default)"),
    Mode.REVIEW: ("review", "#b48ead", "Read-only analysis — writes REVIEW.md"),
}

# ANSI-256 colour codes for the prompt badge (approximate hex matches above)
_PROMPT_ANSI: dict[Mode, int] = {
    Mode.CHAT:   110,   # light blue
    Mode.PLAN:   222,   # yellow
    Mode.CODE:   150,   # green
    Mode.HYBRID: 173,   # orange
    Mode.REVIEW: 139,   # purple
}


def mode_label(mode: Mode) -> str:
    return _DISPLAY[mode][0]


def mode_colour(mode: Mode) -> str:
    return _DISPLAY[mode][1]


def mode_description(mode: Mode) -> str:
    return _DISPLAY[mode][2]


def prompt_ansi_code(mode: Mode) -> int:
    return _PROMPT_ANSI.get(mode, 173)


def parse_mode(value: str) -> Mode | None:
    """Parse a mode string case-insensitively. Returns None if unrecognised."""
    try:
        return Mode(value.strip().lower())
    except ValueError:
        return None


ALL_MODES: list[Mode] = list(Mode)
