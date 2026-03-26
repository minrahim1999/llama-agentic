"""Interactive UI tools — let the agent ask the user structured questions."""
from __future__ import annotations

import json
from agent.tools import tool


@tool
def ask_choice(question: str, options: str, multi: bool = False) -> str:
    """Ask the user to choose from a list of options using an interactive arrow-key selector.

    Use this whenever you have 2+ options and want the user to pick instead of
    guessing. For yes/no or single picks use multi=false; for 'select all that
    apply' use multi=true (Space toggles, Enter confirms).

    Args:
        question: The question or prompt to display to the user.
        options: Newline-separated list of choices, one per line.
        multi: If true, the user can select multiple options (Space to toggle, Enter to confirm). Default false.
    """
    from agent.prompt_ui import select_one, select_many

    opts = [o.strip() for o in options.strip().splitlines() if o.strip()]
    if not opts:
        return "Error: no options provided."

    if multi:
        chosen = select_many(question, opts)
        if not chosen:
            return "User cancelled the selection."
        return "User selected: " + ", ".join(chosen)
    else:
        chosen = select_one(question, opts)
        if chosen is None:
            return "User cancelled the selection."
        return f"User selected: {chosen}"


@tool
def ask_questions(questions_json: str) -> str:
    """Ask the user a sequence of choice questions, then show a summary and ask for final confirmation.

    Use this when you need answers to several questions before proceeding —
    the user sees all their answers together and can confirm or start over.
    After confirmation the answers are returned so you can act on them.

    Args:
        questions_json: JSON array of question objects. Each object must have:
            "question" (string) — the prompt text,
            "options"  (array of strings) — the choices,
            "multi"    (boolean, optional) — allow multiple selections, default false.
            Example: [{"question": "Which framework?", "options": ["React", "Vue", "Svelte"]}, {"question": "Features?", "options": ["TypeScript", "Testing", "CI/CD"], "multi": true}]
    """
    from agent.prompt_ui import ask_sequence

    try:
        raw = json.loads(questions_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid questions_json — {e}"

    if not isinstance(raw, list) or not raw:
        return "Error: questions_json must be a non-empty JSON array."

    # Normalise each question object
    questions = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return f"Error: item {i} is not an object."
        if "question" not in item or "options" not in item:
            return f"Error: item {i} missing 'question' or 'options'."
        questions.append({
            "question": str(item["question"]),
            "options":  [str(o) for o in item["options"]],
            "multi":    bool(item.get("multi", False)),
        })

    answers = ask_sequence(questions)
    if answers is None:
        return "User cancelled — no action taken."

    # Return a readable summary + JSON for the agent to parse
    lines = ["User confirmed the following selections:"]
    for ans in answers:
        val = ans["answer"]
        display = ", ".join(val) if isinstance(val, list) else val
        lines.append(f"  {ans['question']}: {display}")
    lines.append("")
    lines.append("answers_json: " + json.dumps(answers, ensure_ascii=False))
    return "\n".join(lines)
