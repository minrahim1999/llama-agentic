"""Python code execution tool (subprocess-isolated)."""

import subprocess
import sys
from agent.tools import tool


@tool
def run_python(code: str, timeout: int = 30) -> str:
    """Execute Python code in an isolated subprocess and return the output.

    Args:
        code: Python source code to execute.
        timeout: Maximum seconds to wait before killing the process.
    """
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    if not output:
        output = f"(exit code {result.returncode})"
    return output.strip()
