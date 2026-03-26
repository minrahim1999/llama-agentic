"""Think tool — lets the agent reason before acting."""

from agent.tools import tool


@tool
def think(reasoning: str) -> str:
    """Reason through a problem before taking action.

    Use this tool to think step-by-step before making irreversible changes,
    running multi-step tasks, or when the intent is ambiguous.  The reasoning
    is shown to the user but does NOT affect the environment — it is purely a
    scratchpad.

    Call this tool BEFORE calling write_file, edit_file, run_shell, run_python,
    delete_file, or git_commit whenever the action is non-trivial.

    Args:
        reasoning: Step-by-step analysis, plan, or self-check.  Be specific:
            name the files you will touch, the commands you will run, and any
            risks or edge cases you have considered.
    """
    return reasoning
