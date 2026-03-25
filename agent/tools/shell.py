"""Shell execution tool."""

import subprocess
import sys
from agent.tools import tool


@tool
def run_shell(command: str, timeout: int = 30) -> str:
    """Run a shell command and stream its output in real-time.

    Args:
        command: Shell command to execute.
        timeout: Maximum seconds to wait before killing the process.
    """
    lines: list[str] = []

    proc = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(f"  {line}")
            sys.stdout.flush()
            lines.append(line)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        lines.append(f"\n[killed after {timeout}s timeout]")

    output = "".join(lines).strip()
    if not output:
        output = f"(exit code {proc.returncode})"
    return output
