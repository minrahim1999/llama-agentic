"""Interactive terminal choice prompts.

Provides arrow-key navigation, space-to-toggle multi-select, and a
sequential-question flow with summary + final confirmation.

Falls back to numbered input when prompt_toolkit is unavailable.
"""
from __future__ import annotations

import json

# Project accent colour (kept local to avoid circular imports)
_ACCENT  = "#d08770"
_MUTED   = "#808080"
_SEL_FG  = "#7dcfff"
_CUR_BG  = "#1e3a5f"


# ── Core selector ─────────────────────────────────────────────────────────────

def _selector(question: str, options: list[str], multi: bool) -> list[int]:
    """Render an interactive selector; return sorted list of chosen indices."""
    try:
        return _pt_selector(question, options, multi)
    except Exception:
        return _fallback_selector(question, options, multi)


def _pt_selector(question: str, options: list[str], multi: bool) -> list[int]:
    from prompt_toolkit import Application
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    cursor: list[int] = [0]
    chosen: set[int]  = set()

    def render() -> FormattedText:
        parts: list[tuple[str, str]] = []

        # ── Question header ──────────────────────────────────────────────────
        parts += [
            ("class:accent bold", "  ?  "),
            ("bold", f"{question}\n"),
        ]
        if multi:
            parts.append(("class:muted", "     ↑/↓ navigate   Space select/deselect   Enter confirm\n\n"))
        else:
            parts.append(("class:muted", "     ↑/↓ navigate   Enter select\n\n"))

        # ── Option rows ──────────────────────────────────────────────────────
        for i, opt in enumerate(options):
            is_cur = i == cursor[0]
            is_sel = i in chosen

            if multi:
                arrow     = "❯ " if is_cur else "  "
                dot       = "●" if is_sel else "○"
                dot_style = "class:sel bold" if is_sel else "class:muted"
                row_style = "class:cur bold" if is_cur else ""
                parts += [
                    ("class:accent bold" if is_cur else "class:muted", f"  {arrow}"),
                    (dot_style, f"{dot}  "),
                    (row_style, f"{opt}\n"),
                ]
            else:
                arrow     = "❯" if is_cur else " "
                row_style = "class:cur bold" if is_cur else ""
                parts += [
                    ("class:accent bold" if is_cur else "class:muted", f"  {arrow}  "),
                    (row_style, f"{opt}\n"),
                ]

        # ── Selection summary (multi only) ───────────────────────────────────
        if multi and chosen:
            names = ", ".join(options[i] for i in sorted(chosen))
            parts += [
                ("", "\n"),
                ("class:muted", "  Selected: "),
                ("class:sel bold", f"{names}\n"),
            ]
        else:
            parts.append(("", "\n"))

        return FormattedText(parts)

    kb = KeyBindings()

    @kb.add("up")
    def _(e): cursor[0] = (cursor[0] - 1) % len(options)

    @kb.add("down")
    def _(e): cursor[0] = (cursor[0] + 1) % len(options)

    @kb.add("space")
    def _(e):
        if multi:
            if cursor[0] in chosen:
                chosen.discard(cursor[0])
            else:
                chosen.add(cursor[0])
        else:
            chosen.clear()
            chosen.add(cursor[0])
            e.app.exit(result=sorted(chosen))

    @kb.add("enter")
    def _(e):
        if not multi:
            chosen.clear()
            chosen.add(cursor[0])
        e.app.exit(result=sorted(chosen))

    @kb.add("c-c")
    @kb.add("escape")
    def _(e): e.app.exit(result=[])

    style = Style.from_dict({
        "accent": _ACCENT,
        "muted":  _MUTED,
        "cur":    f"bg:{_CUR_BG}",
        "sel":    _SEL_FG,
    })

    app = Application(
        layout=Layout(Window(
            FormattedTextControl(render, focusable=True),
            dont_extend_height=True,
        )),
        key_bindings=kb,
        style=style,
        full_screen=False,
        mouse_support=False,
    )
    return app.run() or []


def _fallback_selector(question: str, options: list[str], multi: bool) -> list[int]:
    """Numbered fallback when prompt_toolkit Application is unavailable."""
    print(f"\n  ? {question}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}.  {opt}")
    print()
    if multi:
        raw = input("  Numbers separated by spaces › ").strip()
        indices = []
        for tok in raw.split():
            try:
                idx = int(tok) - 1
                if 0 <= idx < len(options):
                    indices.append(idx)
            except ValueError:
                pass
        return sorted(set(indices))
    else:
        while True:
            raw = input("  Enter number › ").strip()
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    return [idx]
            except ValueError:
                pass
            print(f"  Enter a number from 1 to {len(options)}.")


# ── Public API ────────────────────────────────────────────────────────────────

def select_one(question: str, options: list[str]) -> str | None:
    """Single-select prompt. Returns chosen option text, or None if cancelled."""
    indices = _selector(question, options, multi=False)
    return options[indices[0]] if indices else None


def select_many(question: str, options: list[str]) -> list[str]:
    """Multi-select prompt. Returns list of chosen option texts."""
    indices = _selector(question, options, multi=True)
    return [options[i] for i in indices]


# ── Sequential questions with summary ─────────────────────────────────────────

def ask_sequence(
    questions: list[dict],
) -> list[dict] | None:
    """Run a list of questions, show a summary panel, ask for final confirmation.

    Each question dict must have:
        question (str)     — the prompt text
        options  (list)    — the choices
        multi    (bool)    — optional, default False

    Returns a list of answer dicts  {question, answer}  or None if cancelled.
    """
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    import rich.box as rbox

    con = Console()
    answers: list[dict] = []

    for q in questions:
        text    = q["question"]
        opts    = q["options"]
        is_multi = q.get("multi", False)

        if is_multi:
            chosen = select_many(text, opts)
            if not chosen:
                con.print("\n  [dim]Cancelled.[/dim]\n")
                return None
            answers.append({"question": text, "answer": chosen})
        else:
            chosen = select_one(text, opts)
            if chosen is None:
                con.print("\n  [dim]Cancelled.[/dim]\n")
                return None
            answers.append({"question": text, "answer": chosen})

    # ── Summary panel ────────────────────────────────────────────────────────
    con.print()
    table = Table.grid(padding=(0, 2), expand=True)
    table.add_column(style=f"bold {_ACCENT}", no_wrap=True)
    table.add_column(style="bold white")

    for ans in answers:
        q_text = ans["question"]
        val    = ans["answer"]
        if isinstance(val, list):
            display = ", ".join(val)
        else:
            display = val
        table.add_row(q_text, display)

    con.print(Panel(
        table,
        title=Text.assemble(("  Your selections", f"bold {_ACCENT}")),
        title_align="left",
        border_style=_ACCENT,
        box=rbox.ROUNDED,
        padding=(1, 2),
    ))
    con.print()

    # ── Final confirmation ───────────────────────────────────────────────────
    valid = {"1", "2", "3"}
    choices = [
        ("1", "Confirm",     "proceed with these selections"),
        ("2", "Start over",  "answer the questions again"),
        ("3", "Cancel",      "abort"),
    ]
    for key, label, desc in choices:
        row = Text()
        row.append(f"  {key}  ", style=f"bold {_ACCENT}")
        row.append(label, style="bold white")
        row.append(f"  {desc}", style=_MUTED)
        con.print(row)
    con.print()

    while True:
        raw = con.input("  Final confirmation › ").strip()
        if raw == "1":
            return answers
        if raw == "2":
            return ask_sequence(questions)   # recurse to restart
        if raw == "3":
            con.print("  [dim]Cancelled.[/dim]\n")
            return None
        con.print(f"  [dim]Enter 1, 2, or 3.[/dim]")
